"""J-Quants (+ yfinance フォールバック) から株価を取得し DataFrame 変換。"""
from __future__ import annotations

import time
from datetime import datetime, timedelta

import pandas as pd
import requests

from mcp_server._api import _headers
from mcp_server._context import (
    yf, _YF_AVAILABLE, REQUEST_SLEEP_SEC, MAX_RETRIES, RETRY_SLEEP_SEC,
)
from mcp_server._db import (
    _init_db, _save_daily_db, _load_daily_db, _save_weekly, _load_weekly,
)


def _fetch_daily_yf(code_4: str) -> list:
    """yfinance で日本株の日足を取得（J-Quants フォールバック用）。
    ティッカー: {4桁コード}.T  例: 6758.T (ソニー)
    15〜20分遅延。J-Quants が失敗した場合のみ使用。
    戻り値: J-Quants 互換の bars リスト形式に変換して返す。
    """
    if not _YF_AVAILABLE:
        return []
    try:
        ticker = yf.Ticker(f"{code_4}.T")
        df = ticker.history(period="400d", auto_adjust=True)
        if df.empty:
            return []
        df = df.reset_index()
        bars = []
        for _, row in df.iterrows():
            dt = row["Date"]
            date_str = dt.strftime("%Y-%m-%d") if hasattr(dt, "strftime") else str(dt)[:10]
            bars.append({
                "Date": date_str,
                "O": float(row["Open"]),
                "H": float(row["High"]),
                "L": float(row["Low"]),
                "C": float(row["Close"]),
                "Vo": int(row["Volume"]),
                # J-Quants互換キー (yfinanceはauto_adjust=Trueで調整済み)
                "AdjO": float(row["Open"]),
                "AdjH": float(row["High"]),
                "AdjL": float(row["Low"]),
                "AdjC": float(row["Close"]),
                "AdjVo": int(row["Volume"]),
            })
        return bars
    except Exception:
        return []


def _fetch_daily(code_4: str, days: int = 2000) -> list:
    """Fetch daily OHLCV from J-Quants V2. Standard plan supports ~5+ years.
    失敗時は yfinance にフォールバック（15分遅延）。
    2000日 ≈ 5.5年 → 中長期トレンド分析に対応"""
    code_5    = code_4 + "0"
    date_from = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")
    date_to   = datetime.now().strftime("%Y%m%d")
    url = (f"https://api.jquants.com/v2/equities/bars/daily"
           f"?code={code_5}&from={date_from}&to={date_to}")
    try:
        resp = requests.get(url, headers=_headers(), timeout=30)
        resp.raise_for_status()
        bars = resp.json().get("data", [])
        if bars:
            return bars
    except Exception:
        pass
    # J-Quants 失敗 → yfinance フォールバック
    return _fetch_daily_yf(code_4)

def _daily_to_weekly(bars: list) -> pd.DataFrame:
    df = pd.DataFrame(bars)
    df["date"] = pd.to_datetime(df["Date"])
    df = df.sort_values("date").set_index("date")
    df["open"]   = df.get("AdjO", df["O"])
    df["high"]   = df.get("AdjH", df["H"])
    df["low"]    = df.get("AdjL", df["L"])
    df["close"]  = df.get("AdjC", df["C"])
    df["volume"] = df.get("AdjVo", df["Vo"])
    return df[["open","high","low","close","volume"]].resample("W-FRI").agg({
        "open": "first", "high": "max", "low": "min",
        "close": "last", "volume": "sum",
    }).dropna()

def _daily_to_df(bars: list) -> pd.DataFrame:
    df = pd.DataFrame(bars)
    df["date"] = pd.to_datetime(df["Date"])
    df = df.sort_values("date").set_index("date")
    df["open"]   = df.get("AdjO", df["O"])
    df["high"]   = df.get("AdjH", df["H"])
    df["low"]    = df.get("AdjL", df["L"])
    df["close"]  = df.get("AdjC", df["C"])
    df["volume"] = df.get("AdjVo", df["Vo"])
    return df[["open","high","low","close","volume"]]

# ---------------------------------------------------------------------------
# Minervini Trend Template (7 conditions, daily SMA 50/150/200)
# ---------------------------------------------------------------------------

