"""stock_mcp_server.py  v2.0

J-Quants stock analysis MCP server for personal investment dashboard.

大型リファクタ (Phase C): 実体は mcp_server/ パッケージに分割中。
本ファイルは現状以下を担う:
- mcp_server._context の import（FastMCP インスタンス取得）
- 未移設の helper / tool 群（段階的に mcp_server/*.py へ移行予定）
- MCP サーバー起動: mcp.run()
"""
from __future__ import annotations

import sqlite3
import subprocess
import os
import time
import json
import threading
import webbrowser
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from datetime import datetime, timedelta

import requests
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ── mcp_server パッケージから共通 context を import ──
from mcp_server._context import (
    mcp,
    yf, _YF_AVAILABLE,
    BASE_DIR, DB_PATH, CSV_DIR, CONFIG,
    PROGRESS_FILE, RESULTS_FILE, MASTER_CACHE, PORTFOLIO_FILE, WATCHLIST_FILE,
    GITHUB_DIR, CHART_DIR,
    MASTER_CACHE_TTL_DAYS, BATCH_SIZE, BATCH_SLEEP_SEC, REQUEST_SLEEP_SEC,
    MAX_RETRIES, RETRY_SLEEP_SEC, PARALLEL_WORKERS,
    NIKKEI225_CODE, ETF_CODE_PREFIXES, MAJOR_STOCKS,
    _job_lock, _job_state,
)


# ---------------------------------------------------------------------------

def _get_api_key() -> str:
    key = os.environ.get("JQUANTS_API_KEY", "")
    if key:
        return key
    if CONFIG.exists():
        data = json.loads(CONFIG.read_text(encoding="utf-8"))
        return data.get("jquants_api_key", "")
    raise RuntimeError(
        "J-Quants API key not found. "
        "Create ~/.jquants_config.json with {\"jquants_api_key\": \"YOUR_KEY\"}"
    )

def _headers() -> dict:
    return {"x-api-key": _get_api_key()}

# ---------------------------------------------------------------------------
# DB init
# ---------------------------------------------------------------------------

def _init_db():
    CSV_DIR.mkdir(parents=True, exist_ok=True)
    (BASE_DIR / "data").mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.execute("""
        CREATE TABLE IF NOT EXISTS weekly_prices (
            code TEXT, date TEXT,
            open REAL, high REAL, low REAL, close REAL, volume REAL,
            PRIMARY KEY (code, date)
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS daily_prices (
            code TEXT, date TEXT,
            open REAL, high REAL, low REAL, close REAL, volume REAL,
            PRIMARY KEY (code, date)
        )
    """)
    con.commit()
    con.close()

def _save_weekly(code: str, df: pd.DataFrame):
    con = sqlite3.connect(DB_PATH)
    df_save = df.reset_index()
    df_save.columns = [c.lower() for c in df_save.columns]
    df_save["code"] = code
    df_save.to_sql("weekly_prices", con, if_exists="replace",
                   index=False, method="multi")
    con.close()

def _load_weekly(code: str) -> pd.DataFrame:
    con = sqlite3.connect(DB_PATH)
    df  = pd.read_sql(
        "SELECT * FROM weekly_prices WHERE code=? ORDER BY date",
        con, params=(code,)
    )
    con.close()
    return df


def _save_daily_db(code: str, df: pd.DataFrame):
    """Save daily OHLCV to SQLite (upsert / append, no data loss)."""
    _init_db()
    con = sqlite3.connect(DB_PATH)
    df_save = df.reset_index()
    df_save.columns = [c.lower() for c in df_save.columns]
    df_save["code"] = code
    df_save["date"] = df_save["date"].astype(str).str[:10]
    # INSERT OR REPLACE to merge new data with existing
    for _, row in df_save.iterrows():
        con.execute(
            "INSERT OR REPLACE INTO daily_prices "
            "(code, date, open, high, low, close, volume) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (row["code"], row["date"],
             row["open"], row["high"], row["low"], row["close"], row["volume"]),
        )
    con.commit()
    con.close()


def _load_daily_db(code: str) -> pd.DataFrame:
    """Load daily OHLCV from SQLite (all historical data)."""
    _init_db()
    con = sqlite3.connect(DB_PATH)
    df = pd.read_sql(
        "SELECT date, open, high, low, close, volume "
        "FROM daily_prices WHERE code=? ORDER BY date",
        con, params=(code,),
    )
    con.close()
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date")
    return df

# ---------------------------------------------------------------------------
# Fetch helpers
# ---------------------------------------------------------------------------

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

def _minervini(daily_df: pd.DataFrame) -> dict:
    c = daily_df["close"].values.astype(float)
    if len(c) < 52:
        return {"error": f"only {len(c)} trading days (need >= 52)"}

    price     = c[-1]
    sma50     = c[-min(50,  len(c)):].mean()
    sma150    = c[-min(150, len(c)):].mean()
    sma200    = c[-min(200, len(c)):].mean()
    sma200_1m = c[-min(220, len(c)):-20].mean() if len(c) >= 30 else sma200 * 0.999
    high52    = c[-min(252, len(c)):].max()
    low52     = c[-min(252, len(c)):].min()

    cond = [
        bool(price > sma150 and price > sma200),   # 1
        bool(sma150 > sma200),                      # 2
        bool(sma200 > sma200_1m),                   # 3
        bool(sma50 > sma150 and sma50 > sma200),   # 4
        bool(price > sma50),                        # 5
        bool(price > low52 * 1.25),                 # 6
        bool(price > high52 * 0.75),                # 7
    ]
    n = sum(cond)
    return {
        "passed":     n >= 6,
        "score":      f"{n}/7",
        "conditions": cond,
        "price":      round(float(price), 1),
        "sma50":      round(float(sma50), 1),
        "sma150":     round(float(sma150), 1),
        "sma200":     round(float(sma200), 1),
        "high52":     round(float(high52), 1),
        "low52":      round(float(low52), 1),
        "days":       len(c),
    }

# ---------------------------------------------------------------------------
# RS (Relative Strength) vs Nikkei225
# ---------------------------------------------------------------------------

def _calc_rs(stock_weekly_closes: list, bench_weekly_closes: list) -> dict:
    """
    週足ベースのRelative Strength計算。
    日足50/150/250本を週足に換算: n=10w/30w/50w
      10週 ≈ 50日(2.5ヶ月)
      30週 ≈ 150日(6ヶ月)
      50週 ≈ 250日(1年)
    計算式: (1 + stock_return) / (1 + bench_return)
      RS > 1.0 = アウトパフォーム
      RS < 1.0 = アンダーパフォーム
    旧式 stock_return/bench_return は下落相場で符号が反転するバグあり → 修正済み
    """
    def _rs(stock, bench, n):
        if len(stock) < n + 1 or len(bench) < n + 1:
            return None
        sr = stock[-1] / stock[-n - 1] - 1.0
        br = bench[-1] / bench[-n - 1] - 1.0
        if br == -1.0:
            return None
        return round((1.0 + sr) / (1.0 + br), 3)

    s = stock_weekly_closes
    b = bench_weekly_closes

    return {
        "rs10w":  _rs(s, b, 10),  # ≈50日(2.5ヶ月)
        "rs30w":  _rs(s, b, 30),  # ≈150日(6ヶ月)
        "rs50w":  _rs(s, b, 50),  # ≈250日(1年)
    }

# ---------------------------------------------------------------------------
# Fundamental data
# ---------------------------------------------------------------------------

def _fetch_fins(code_4: str) -> dict:
    """
    Fetch latest financial summary from /v2/fins/summary (V2 short field names).
    V2 field mapping: Sales/OP/NP/EPS/BPS/Eq/TA/FcstSales/FcstNP/FcstEPS
    Response key: "summary"
    """
    code_5 = code_4 + "0"
    url    = f"https://api.jquants.com/v2/fins/summary?code={code_5}"
    try:
        resp = requests.get(url, headers=_headers(), timeout=30)
        resp.raise_for_status()
        # V2レスポンスキーは "data"
        items = resp.json().get("data", [])
        if not items:
            return {}
        # 通期(FY)の直近データを優先、なければ最新
        fy_items = [i for i in items if i.get("CurPerType") == "FY"]
        latest   = fy_items[-1] if fy_items else items[-1]

        def _num(v):
            if v is None or v == "": return None
            try: return float(v)
            except: return None

        return {
            "fiscal_year":     latest.get("CurFYEn", "")[:7],
            "period":          latest.get("CurPerType", ""),
            "disclosed_date":  latest.get("DiscDate", ""),
            "sales":           _num(latest.get("Sales")),
            "op_profit":       _num(latest.get("OP")),
            "ord_profit":      _num(latest.get("OdP")),
            "net_profit":      _num(latest.get("NP")),
            "eps":             _num(latest.get("EPS")),
            "bps":             _num(latest.get("BPS")),
            "equity":          _num(latest.get("Eq")),
            "total_assets":    _num(latest.get("TA")),
            "equity_ratio":    _num(latest.get("EqAR")),
            "forecast_sales":  _num(latest.get("FcstSales")),
            "forecast_profit": _num(latest.get("FcstNP")),
            "forecast_eps":    _num(latest.get("FcstEPS")),
            "div_annual":      _num(latest.get("DivAnn")),
        }
    except Exception:
        return {}

def _fetch_fins_history(code_4: str) -> list:
    """Fetch all financial records from J-Quants (FY + quarterly, ~10 years)."""
    code_5 = code_4 + "0"
    url = f"https://api.jquants.com/v2/fins/summary?code={code_5}"
    try:
        resp = requests.get(url, headers=_headers(), timeout=30)
        resp.raise_for_status()
        items = resp.json().get("data", [])
    except Exception:
        return []

    def _num(v):
        if v is None or v == "":
            return None
        try:
            return float(v)
        except (ValueError, TypeError):
            return None

    records = []
    for item in items:
        fy_end = item.get("CurFYEn", "")
        per_type = item.get("CurPerType", "")
        if not fy_end or not per_type:
            continue
        records.append({
            "fy": fy_end[:7],            # e.g. "2026-03"
            "period": per_type,           # FY, 1Q, 2Q, 3Q
            "date": item.get("DiscDate", ""),
            "sales": _num(item.get("Sales")),
            "op": _num(item.get("OP")),
            "np": _num(item.get("NP")),
            "eps": _num(item.get("EPS")),
            "bps": _num(item.get("BPS")),
            "div": _num(item.get("DivAnn")),
            "eq_ratio": _num(item.get("EqAR")),
            # Forecasts (current FY)
            "f_sales": _num(item.get("FSales")),
            "f_op": _num(item.get("FOP")),
            "f_np": _num(item.get("FNP")),
            "f_eps": _num(item.get("FEPS")),
            # Next FY forecasts
            "nf_sales": _num(item.get("NxFSales")),
            "nf_op": _num(item.get("NxFOP")),
            "nf_np": _num(item.get("NxFNp")),
            "nf_eps": _num(item.get("NxFEPS")),
        })
    return records


# ---------------------------------------------------------------------------
# ETF detection
# ---------------------------------------------------------------------------

def _is_etf(code_4: str, item: dict = None) -> bool:
    if str(code_4).startswith(ETF_CODE_PREFIXES):
        return True
    if item:
        tc        = str(item.get("TypeCode", ""))
        etf_types = {"ETF", "REIT", "ETN", "InfFund", "PRF"}
        if any(t.lower() in tc.lower() for t in etf_types):
            return True
    return False

# ---------------------------------------------------------------------------
# Equity master
# ---------------------------------------------------------------------------

def fetch_equity_master(force: bool = False) -> list:
    if not force and MASTER_CACHE.exists():
        cached    = json.loads(MASTER_CACHE.read_text(encoding="utf-8"))
        cached_at = datetime.fromisoformat(cached["fetched_at"])
        if datetime.now() - cached_at < timedelta(days=MASTER_CACHE_TTL_DAYS):
            return cached["items"]

    resp = requests.get("https://api.jquants.com/v2/equities/master",
                        headers=_headers(), timeout=30)
    resp.raise_for_status()
    data     = resp.json()
    items    = data.get("info", data.get("data", []))
    equities = [
        i for i in items
        if len(str(i.get("Code", ""))) == 5
        and str(i.get("Code", ""))[-1] == "0"
    ]
    (BASE_DIR / "data").mkdir(parents=True, exist_ok=True)
    MASTER_CACHE.write_text(
        json.dumps({"fetched_at": datetime.now().isoformat(),
                    "count": len(equities), "items": equities},
                   ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    return equities

def _lookup_name(code_4: str) -> str:
    if not MASTER_CACHE.exists():
        return ""
    master = json.loads(MASTER_CACHE.read_text(encoding="utf-8"))
    code_5 = code_4 + "0"
    for item in master.get("items", []):
        if str(item.get("Code", "")) == code_5:
            # V2短縮形: CoNameEn / CoName、旧V1: CompanyNameEnglish / CompanyName
            return (item.get("CoNameEn")
                    or item.get("CoName")
                    or item.get("CompanyNameEnglish")
                    or item.get("CompanyName", ""))
    return ""
    return ""

# ---------------------------------------------------------------------------
# screen_full helpers
# ---------------------------------------------------------------------------

def _load_progress() -> dict:
    if PROGRESS_FILE.exists():
        return json.loads(PROGRESS_FILE.read_text(encoding="utf-8"))
    return {"last_index": 0, "started_at": None, "total": 0}

def _save_progress(index: int, total: int, started_at: str):
    PROGRESS_FILE.write_text(
        json.dumps({"last_index": index, "total": total,
                    "started_at": started_at}, ensure_ascii=False),
        encoding="utf-8"
    )

def _load_results() -> dict:
    if RESULTS_FILE.exists():
        return json.loads(RESULTS_FILE.read_text(encoding="utf-8"))
    return {}

def _save_results(results: dict):
    RESULTS_FILE.write_text(
        json.dumps(results, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

def _screen_one_with_retry(code_4: str, bench_weekly_closes: list = None) -> dict:
    for attempt in range(MAX_RETRIES):
        try:
            time.sleep(REQUEST_SLEEP_SEC)
            bars = _fetch_daily(code_4)
            if not bars or len(bars) < 10:
                return {"code": code_4, "error": "insufficient data"}

            daily_df  = _daily_to_df(bars)
            result    = _minervini(daily_df)
            if "error" in result:
                return {"code": code_4, "error": result["error"]}

            # RS計算（週足 n=10/30/50w ≈ 日足50/150/250日）
            rs = {}
            if bench_weekly_closes and len(bench_weekly_closes) > 10:
                weekly_df           = _daily_to_weekly(bars)
                stock_weekly_closes = weekly_df["close"].tolist()
                rs = _calc_rs(stock_weekly_closes, bench_weekly_closes)

            return {
                "code":       code_4,
                "name":       _lookup_name(code_4),
                "price":      result["price"],
                "passed":     result["passed"],
                "score":      result["score"],
                "high52":     result["high52"],
                "low52":      result["low52"],
                "sma50":      result["sma50"],
                "sma150":     result["sma150"],
                "sma200":     result["sma200"],
                "conditions": result["conditions"],
                "rs10w":      rs.get("rs10w"),
                "rs30w":      rs.get("rs30w"),
                "rs50w":      rs.get("rs50w"),
            }

        except Exception as e:
            err = str(e)
            if "429" in err or "rate" in err.lower():
                time.sleep(RETRY_SLEEP_SEC * (attempt + 1))
            elif attempt == MAX_RETRIES - 1:
                return {"code": code_4, "error": err}
            else:
                time.sleep(RETRY_SLEEP_SEC)
    return {"code": code_4, "error": "max retries exceeded"}

# ---------------------------------------------------------------------------
# Background worker
# ---------------------------------------------------------------------------

def _run_screen_full_bg(codes: list, total: int, resume: bool, started_at: str):
    global _job_state

    # Nikkei225ベンチマーク取得（400日→57週、n=50週に十分）
    bench_weekly_closes = []
    try:
        bench_bars          = _fetch_daily(NIKKEI225_CODE)
        bench_weekly_df     = _daily_to_weekly(bench_bars)
        bench_weekly_closes = bench_weekly_df["close"].tolist()
    except Exception:
        pass

    results   = _load_results() if resume else {}
    start_idx = 0
    if resume:
        prog      = _load_progress()
        start_idx = prog.get("last_index", 0)

    errors = 0

    # 未処理コードのみ抽出
    pending = [c for c in codes[start_idx:]
               if not (c in results and not results[c].get("error"))]
    # 既処理分をカウントに反映
    already_done = total - len(pending) - start_idx + \
                   sum(1 for c in codes[start_idx:] if c in results and not results[c].get("error"))

    with _job_lock:
        _job_state["done"] = start_idx + (total - start_idx - len(pending))

    try:
        # ThreadPoolExecutorで並列処理
        with ThreadPoolExecutor(max_workers=PARALLEL_WORKERS) as executor:
            future_to_code = {
                executor.submit(_screen_one_with_retry, code, bench_weekly_closes): code
                for code in pending
            }

            batch_count = 0
            for future in as_completed(future_to_code):
                # 停止チェック
                with _job_lock:
                    if not _job_state["running"]:
                        executor.shutdown(wait=False)
                        _save_results(results)
                        return

                code = future_to_code[future]
                try:
                    res = future.result()
                except Exception as e:
                    res = {"code": code, "error": str(e)}

                results[code] = res
                batch_count  += 1

                with _job_lock:
                    _job_state["done"]     += 1
                    _job_state["last_code"] = code
                    if res.get("error"):
                        errors += 1
                        _job_state["errors"] = errors
                    elif res.get("passed"):
                        _job_state["passed"] += 1

                # BATCH_SIZE件ごとに保存
                if batch_count % BATCH_SIZE == 0:
                    done_count = _job_state["done"]
                    _save_progress(done_count, total, started_at)
                    _save_results(results)

        # 完了
        _save_progress(total, total, started_at)
        finished_at = datetime.now().isoformat()
        elapsed_min = round(
            (datetime.now() - datetime.fromisoformat(started_at)).total_seconds() / 60, 1
        )
        pass_count = sum(1 for k, v in results.items()
                         if k != "__meta__" and v.get("passed"))

        results["__meta__"] = {
            "started_at":  started_at,
            "finished_at": finished_at,
            "elapsed_min": elapsed_min,
            "total":       total,
            "passed":      pass_count,
            "errors":      errors,
        }
        _save_results(results)

        with _job_lock:
            _job_state.update({
                "running":     False,
                "status":      "complete",
                "finished_at": finished_at,
                "elapsed_min": elapsed_min,
            })

    except Exception as e:
        with _job_lock:
            _job_state["running"] = False
            _job_state["status"]  = f"error: {e}"

    except Exception as e:
        with _job_lock:
            _job_state["running"] = False
            _job_state["status"]  = f"error: {e}"

# ---------------------------------------------------------------------------
# ============================================================
# MCP TOOLS
# ============================================================
# ---------------------------------------------------------------------------

# ── 1. 株価取得 ──────────────────────────────────────────────

@mcp.tool()
def fetch_stock(code: str) -> str:
    """
    Fetch stock price data from J-Quants API and save to DB/CSV.
    Example: fetch_stock("6758")
    """
    _init_db()
    try:
        bars = _fetch_daily(code)
        if not bars:
            return f"ERROR {code}: no data returned"

        weekly    = _daily_to_weekly(bars)
        _save_weekly(code, weekly)
        (CSV_DIR / f"{code}_weekly.csv").write_text(
            weekly.reset_index().to_csv(index=False), encoding="utf-8"
        )
        daily_df = _daily_to_df(bars)
        (CSV_DIR / f"{code}_daily.csv").write_text(
            daily_df.reset_index().to_csv(index=False), encoding="utf-8"
        )
        last_close = daily_df["close"].iloc[-1]
        return (f"OK {code}: {len(bars)} daily -> {len(weekly)} weekly, "
                f"last close: {last_close:.0f}")
    except Exception as e:
        return f"ERROR {code}: {e}"


@mcp.tool()
def screen_stock(code: str) -> str:
    """
    Apply Minervini trend template + RS to a single stock.
    Example: screen_stock("6758")
    """
    daily_csv = CSV_DIR / f"{code}_daily.csv"
    if daily_csv.exists():
        df = pd.read_csv(daily_csv, parse_dates=["date"]).set_index("date")
    else:
        df = _load_weekly(code)
        if df.empty:
            return f"No data for {code}. Run fetch_stock first."
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date").set_index("date")

    result = _minervini(df)
    if "error" in result:
        return f"Screen {code}: {result['error']}"

    cond_names = [
        "Price > SMA150 & SMA200",
        "SMA150 > SMA200",
        "SMA200 rising 1M",
        "SMA50 > SMA150 & SMA200",
        "Price > SMA50",
        "Price > 52wLow + 25%",
        "Price > 52wHigh - 25%",
    ]
    status = "PASS" if result["passed"] else "FAIL"
    lines  = [
        f"[{code}] {result['score']} {status}",
        f"  Price : {result['price']:,.0f}  "
        f"SMA50:{result['sma50']:,.0f}  SMA150:{result['sma150']:,.0f}  "
        f"SMA200:{result['sma200']:,.0f}",
        f"  52w   : High {result['high52']:,.0f}  Low {result['low52']:,.0f}  "
        f"({result['days']} days)",
        "",
    ]
    for ok, name in zip(result["conditions"], cond_names):
        lines.append(f"  {'✓' if ok else '✗'} {name}")
    return "\n".join(lines)


@mcp.tool()
def screen_all(top_n: int = 20) -> str:
    """
    Screen major stocks (20 default). Example: screen_all(20)
    """
    _init_db()
    codes   = MAJOR_STOCKS[:top_n]
    results = []
    for code in codes:
        try:
            bars = _fetch_daily(code)
            if bars:
                _save_weekly(code, _daily_to_weekly(bars))
                r = _minervini(_daily_to_df(bars))
                if "error" not in r:
                    results.append((code, r))
            time.sleep(REQUEST_SLEEP_SEC)
        except Exception:
            pass

    results.sort(key=lambda x: -int(x[1]["score"].split("/")[0]))
    passed = sum(1 for _, r in results if r["passed"])
    lines  = [f"Screened {len(results)} stocks  |  PASS: {passed}\n",
              f"  {'Code':<6}  {'Price':>8}  {'Score'}  {'High52':>8}  {'高値比':>6}",
              f"  {'-'*45}"]
    for code, r in results:
        mk     = ">>" if r["passed"] else "  "
        pct    = f"{r['price']/r['high52']*100:.1f}%" if r["high52"] else "  N/A"
        lines.append(f"{mk} {code:<6}  {r['price']:>8,.0f}  {r['score']}  "
                     f"{r['high52']:>8,.0f}  {pct:>6}")
    return "\n".join(lines)


@mcp.tool()
def get_weekly_csv(code: str) -> str:
    """Get weekly OHLCV CSV preview. Example: get_weekly_csv("6758")"""
    csv_path = CSV_DIR / f"{code}_weekly.csv"
    if not csv_path.exists():
        return f"No CSV for {code}. Run fetch_stock first."
    lines   = csv_path.read_text(encoding="utf-8").strip().split("\n")
    preview = "\n".join(lines[:6])
    return f"CSV: {csv_path}\nRows: {len(lines)-1}\n\n{preview}\n..."


@mcp.tool()
def list_stocks() -> str:
    """List all stocks saved in the database."""
    _init_db()
    con  = sqlite3.connect(DB_PATH)
    rows = con.execute(
        "SELECT code, close, date FROM weekly_prices "
        "WHERE date=(SELECT MAX(date) FROM weekly_prices w2 WHERE w2.code=weekly_prices.code) "
        "ORDER BY code"
    ).fetchall()
    con.close()
    if not rows:
        return "No stocks saved. Use fetch_stock to get data."
    lines = [f"Saved {len(rows)} stocks:\n",
             f"  {'Code':<6}  {'Price':>8}  {'Date'}"]
    for code, close, date in rows:
        lines.append(f"  {code:<6}  {close:>8,.0f}  ({date[:10]})")
    return "\n".join(lines)

# ── 2. 全銘柄スクリーニング ──────────────────────────────────

@mcp.tool()
def get_equity_master(force_refresh: bool = False) -> str:
    """
    Download and cache JPX equity master (~4,400 stocks).
    force_refresh=True to bypass 7-day cache.
    """
    items        = fetch_equity_master(force=force_refresh)
    sector_count = {}
    for item in items:
        # V2: S17Nm、旧V1: Sector17CodeName
        s = item.get("S17Nm") or item.get("Sector17CodeName") or "Unknown"
        sector_count[s] = sector_count.get(s, 0) + 1
    top  = sorted(sector_count.items(), key=lambda x: -x[1])[:10]
    sl   = "\n".join(f"  {n}: {c}" for n, c in top)
    return (f"Equity master: {len(items)} stocks\nTop sectors:\n{sl}\n"
            f"Cache: {MASTER_CACHE}")


@mcp.tool()
def screen_full(
    resume:       bool = True,
    max_stocks:   int  = 0,
    sector_filter: str = "",
    exclude_etf:  bool = True,
) -> str:
    """
    Screen ALL JPX-listed stocks with Minervini + RS. Runs in background.
    resume      : continue from last interrupted run (default True).
    max_stocks  : limit for testing, 0 = all (~3800 excl ETF).
    sector_filter: e.g. "Electric Appliances", "Chemicals".
    exclude_etf : exclude ETF/REIT/investment trusts (default True).

    Use screen_full_status()  to monitor progress.
    Use screen_full_results() to query results.
    """
    global _job_state

    with _job_lock:
        if _job_state["running"]:
            done  = _job_state["done"]
            total = _job_state["total"]
            pct   = done / total * 100 if total else 0
            return (f"Already running: {done}/{total} ({pct:.1f}%)\n"
                    f"Use screen_full_status() to check progress.")

    items = fetch_equity_master()
    if exclude_etf:
        items = [i for i in items if not _is_etf(str(i.get("Code",""))[:4], i)]
    if sector_filter:
        items = [i for i in items
                 if sector_filter.lower() in
                    (i.get("S17Nm") or i.get("Sector17CodeName") or "").lower()]

    codes = [str(i["Code"])[:4] for i in items]
    total = len(codes) if max_stocks == 0 else min(max_stocks, len(codes))
    codes = codes[:total]

    if resume:
        prog = _load_progress()
        if prog.get("last_index", 0) >= total and total > 0:
            results    = _load_results()
            meta       = results.get("__meta__", {})
            pass_count = meta.get("passed", sum(
                1 for k, v in results.items()
                if k != "__meta__" and v.get("passed")))
            elapsed    = meta.get("elapsed_min", "?")
            started    = meta.get("started_at", "")[:16]
            return (f"前回完了済み: {total}銘柄  PASS:{pass_count}  "
                    f"所要:{elapsed}分  ({started})\n"
                    f"screen_full_results() で結果確認\n"
                    f"resume=False で再実行")

    started_at = datetime.now().isoformat()
    with _job_lock:
        _job_state.update({
            "running":     True,
            "done":        0,
            "total":       total,
            "passed":      0,
            "errors":      0,
            "started_at":  started_at,
            "finished_at": None,
            "elapsed_min": None,
            "status":      "running",
            "last_code":   "",
        })

    threading.Thread(
        target=_run_screen_full_bg,
        args=(codes, total, resume, started_at),
        daemon=True,
    ).start()

    etf_note = " ETF/REIT除外" if exclude_etf else ""
    return (f"スクリーニング開始: {total}銘柄{etf_note}\n"
            f"screen_full_status() で進捗確認\n"
            f"screen_full_results() で結果確認（完了後）")


# ---------------------------------------------------------------------------
# 一括ダウンロード (V2 API × 高並列)
# V1 daily_quotesはBearer token認証が必要なため、V2を高並列で使用
# ---------------------------------------------------------------------------

_bulk_lock  = threading.Lock()
_bulk_state = {"running": False, "done": 0, "total": 0, "status": "idle",
               "saved": 0, "started_at": None, "error": ""}
BULK_WORKERS = 5  # 並列数（レートリミット対策で5に抑制）

def _download_one_stock(code_4: str) -> tuple:
    """1銘柄の株価をV2 APIで取得してDBに保存。(code, ok) を返す
    リトライロジック付き（429/一時エラーを自動リカバリ）"""
    for attempt in range(MAX_RETRIES):
        try:
            time.sleep(REQUEST_SLEEP_SEC)
            bars = _fetch_daily(code_4)
            if not bars:
                return (code_4, False)
            daily_df  = _daily_to_df(bars)
            weekly_df = _daily_to_weekly(bars)
            _save_daily_db(code_4, daily_df)
            _save_weekly(code_4, weekly_df)
            return (code_4, True)
        except Exception as e:
            err = str(e)
            if "429" in err or "rate" in err.lower():
                time.sleep(RETRY_SLEEP_SEC * (attempt + 1))
            elif attempt == MAX_RETRIES - 1:
                return (code_4, False)
            else:
                time.sleep(RETRY_SLEEP_SEC)
    return (code_4, False)

def _run_bulk_download(workers: int, exclude_etf: bool):
    global _bulk_state
    # 銘柄マスター取得
    try:
        master = fetch_equity_master()
    except Exception as e:
        with _bulk_lock:
            _bulk_state.update({"running": False, "status": "error", "error": str(e)})
        return
    ETF_PREFIXES = ("13", "14", "15", "16", "17", "18", "19")
    codes = []
    for item in master:
        code = str(item.get("Code", ""))
        if not code:
            continue
        if exclude_etf and code[:2] in ETF_PREFIXES:
            continue
        codes.append(code[:4])
    codes = list(dict.fromkeys(codes))  # 重複除去

    with _bulk_lock:
        _bulk_state.update({"running": True, "done": 0, "total": len(codes),
                            "status": "downloading", "saved": 0, "error": "",
                            "started_at": datetime.now().isoformat()})

    saved = 0
    (BASE_DIR / "data").mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(_download_one_stock, c): c for c in codes}
        for future in as_completed(futures):
            with _bulk_lock:
                if not _bulk_state["running"]:
                    executor.shutdown(wait=False)
                    break
            _, ok = future.result()
            if ok:
                saved += 1
            with _bulk_lock:
                _bulk_state["done"] += 1
                _bulk_state["saved"] = saved
    with _bulk_lock:
        _bulk_state.update({"running": False, "status": "done", "saved": saved})


@mcp.tool()
def bulk_download_all(workers: int = 5, exclude_etf: bool = True) -> str:
    """
    全銘柄の株価データをV2 API × 並列でダウンロード。
    workers: 並列数（デフォルト5。20だと429レートリミットで失敗するため5推奨）
    リトライロジック付き（429エラー時は自動待機して再試行）。
    完了後 screen_full() でMinerviniスコアを計算。
    bulk_download_status() で進捗確認。
    """
    with _bulk_lock:
        if _bulk_state["running"]:
            return "既に実行中です。bulk_download_status() で進捗確認してください。"
    t = threading.Thread(target=_run_bulk_download, args=(workers, exclude_etf), daemon=True)
    t.start()
    return (f"一括ダウンロード開始: {workers}並列 × 全銘柄\n"
            f"推定時間: 約{round(4071/workers*REQUEST_SLEEP_SEC/60,1)}分\n"
            f"bulk_download_status() で進捗確認")


@mcp.tool()
def bulk_download_status() -> str:
    """Check progress of bulk_download_all job."""
    with _bulk_lock:
        s = dict(_bulk_state)
    if s["status"] == "idle":
        return "未実行。bulk_download_all() を呼んでください。"
    done, total = s["done"], s["total"]
    pct = round(done / total * 100, 1) if total else 0
    if s["status"] == "downloading":
        elapsed = (datetime.now() - datetime.fromisoformat(s["started_at"])).total_seconds()
        remaining = round((elapsed / done * (total - done)) / 60, 1) if done > 0 else "?"
        return (f"Status  : ダウンロード中\n"
                f"Progress: {done}/{total}日 ({pct}%)\n"
                f"残り    : 約{remaining}分")
    if s["status"] == "saving":
        return f"Status  : DBへ保存中 ({done}/{total}日完了)"
    if s["status"] == "done":
        return (f"Status  : 完了\n"
                f"保存銘柄: {s['saved']}銘柄\n"
                f"次のステップ: screen_full() でMinerviniスコアを計算してください")
    return f"Status: {s['status']}"


# ---------------------------------------------------------------------------
# 財務データ一括ダウンロード
# ---------------------------------------------------------------------------

_fins_lock  = threading.Lock()
_fins_state = {"running": False, "done": 0, "total": 0, "status": "idle",
               "saved": 0, "started_at": None, "error": ""}

FINS_DB_PATH = BASE_DIR / "data" / "fins_data.db"

def _init_fins_db():
    with sqlite3.connect(FINS_DB_PATH) as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS fins (
                code TEXT,
                fy TEXT,
                period TEXT,
                date TEXT,
                sales REAL,
                op REAL,
                np REAL,
                eps REAL,
                bps REAL,
                div REAL,
                equity_ratio REAL,
                forecast_sales REAL,
                forecast_np REAL,
                forecast_eps REAL,
                PRIMARY KEY (code, fy, period)
            )
        """)
        con.commit()

def _save_fins_db(code_4: str, records: list):
    if not records:
        return
    rows = []
    for r in records:
        rows.append((
            code_4, r.get("fy"), r.get("period"), r.get("date"),
            r.get("sales"), r.get("op"), r.get("np"),
            r.get("eps"), r.get("bps"), r.get("div"),
            r.get("equity_ratio"), r.get("forecast_sales"),
            r.get("forecast_np"), r.get("forecast_eps"),
        ))
    with sqlite3.connect(FINS_DB_PATH) as con:
        con.executemany("""
            INSERT OR REPLACE INTO fins VALUES
            (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, rows)
        con.commit()

def _download_one_fins(code_4: str) -> tuple:
    """1銘柄の財務データを取得してDBに保存。(code, ok) を返す
    _fetch_fins_historyは例外を飲み込むため直接HTTPリクエストしてリトライ"""
    code_5 = code_4 + "0"
    url = f"https://api.jquants.com/v2/fins/summary?code={code_5}"
    for attempt in range(MAX_RETRIES):
        try:
            time.sleep(REQUEST_SLEEP_SEC)
            resp = requests.get(url, headers=_headers(), timeout=30)
            resp.raise_for_status()  # 429はここで例外になる
            items = resp.json().get("data", [])
            if not items:
                return (code_4, False)  # 財務データなし（正常な空）
            # _fetch_fins_historyと同じ変換ロジック
            def _num(v):
                if v is None or v == "": return None
                try: return float(v)
                except: return None
            records = []
            for item in items:
                fy_end   = item.get("CurFYEn", "")
                per_type = item.get("CurPerType", "")
                if not fy_end or not per_type:
                    continue
                records.append({
                    "fy": fy_end[:7], "period": per_type,
                    "date": item.get("DiscDate", ""),
                    "sales": _num(item.get("Sales")), "op": _num(item.get("OP")),
                    "np": _num(item.get("NP")), "eps": _num(item.get("EPS")),
                    "bps": _num(item.get("BPS")), "div": _num(item.get("DivAnn")),
                    "equity_ratio":   _num(item.get("EqAR")),
                    "forecast_sales": _num(item.get("FSales")),
                    "forecast_np":    _num(item.get("FNP")),
                    "forecast_eps":   _num(item.get("FEPS")),
                })
            if records:
                _save_fins_db(code_4, records)
                return (code_4, True)
            return (code_4, False)
        except Exception as e:
            err = str(e)
            if "429" in err or "rate" in err.lower():
                time.sleep(RETRY_SLEEP_SEC * (attempt + 1))
            elif attempt == MAX_RETRIES - 1:
                return (code_4, False)
            else:
                time.sleep(RETRY_SLEEP_SEC)
    return (code_4, False)

def _run_bulk_fins(workers: int, exclude_etf: bool):
    global _fins_state
    _init_fins_db()
    try:
        master = fetch_equity_master()
    except Exception as e:
        with _fins_lock:
            _fins_state.update({"running": False, "status": "error", "error": str(e)})
        return
    ETF_PREFIXES = ("13", "14", "15", "16", "17", "18", "19")
    codes = []
    for item in master:
        code = str(item.get("Code", ""))
        if not code:
            continue
        if exclude_etf and code[:2] in ETF_PREFIXES:
            continue
        codes.append(code[:4])
    codes = list(dict.fromkeys(codes))

    with _fins_lock:
        _fins_state.update({"running": True, "done": 0, "total": len(codes),
                            "status": "downloading", "saved": 0, "error": "",
                            "started_at": datetime.now().isoformat()})

    saved = 0
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(_download_one_fins, c): c for c in codes}
        for future in as_completed(futures):
            with _fins_lock:
                if not _fins_state["running"]:
                    executor.shutdown(wait=False)
                    break
            _, ok = future.result()
            if ok:
                saved += 1
            with _fins_lock:
                _fins_state["done"] += 1
                _fins_state["saved"] = saved
    with _fins_lock:
        _fins_state.update({"running": False, "status": "done", "saved": saved})


@mcp.tool()
def bulk_download_fins(workers: int = 5, exclude_etf: bool = True) -> str:
    """
    全銘柄の財務データ（売上/営業利益/EPS/BPS等）をV2 API × 並列でダウンロード。
    データは data/fins_data.db に保存される。
    workers: 並列数（デフォルト5）
    bulk_fins_status() で進捗確認。
    """
    with _fins_lock:
        if _fins_state["running"]:
            return "既に実行中です。bulk_fins_status() で進捗確認してください。"
    t = threading.Thread(target=_run_bulk_fins, args=(workers, exclude_etf), daemon=True)
    t.start()
    return (f"財務データ一括ダウンロード開始: {workers}並列 × 全銘柄\n"
            f"データ保存先: data/fins_data.db\n"
            f"bulk_fins_status() で進捗確認")


@mcp.tool()
def bulk_fins_status() -> str:
    """Check progress of bulk_download_fins job."""
    with _fins_lock:
        s = dict(_fins_state)
    if s["status"] == "idle":
        return "未実行。bulk_download_fins() を呼んでください。"
    done, total = s["done"], s["total"]
    pct = round(done / total * 100, 1) if total else 0
    if s["status"] == "downloading":
        elapsed = (datetime.now() - datetime.fromisoformat(s["started_at"])).total_seconds()
        remaining = round((elapsed / done * (total - done)) / 60, 1) if done > 0 else "?"
        return (f"Status  : ダウンロード中\n"
                f"Progress: {done}/{total}銘柄 ({pct}%)\n"
                f"残り    : 約{remaining}分")
    if s["status"] == "done":
        return (f"Status  : 完了\n"
                f"保存銘柄: {s['saved']}銘柄\n"
                f"保存先  : data/fins_data.db")
    return f"Status: {s['status']}"


@mcp.tool()
def screen_full_status() -> str:
    """Check progress of a running or completed screen_full job."""
    with _job_lock:
        state = dict(_job_state)

    if state["status"] in ("running", "complete"):
        done  = state["done"]
        total = state["total"]
        pct   = done / total * 100 if total else 0

        eta_str = ""
        if state["started_at"] and done > 0 and state["status"] == "running":
            elapsed   = (datetime.now() -
                         datetime.fromisoformat(state["started_at"])).total_seconds()
            remaining = (elapsed / done) * (total - done)
            eta_str   = (f"\n  経過: {elapsed/60:.1f}分  "
                         f"残り: {remaining/60:.1f}分")

        fin_str = ""
        if state["finished_at"]:
            fin_str = (f"\n  完了: {state['finished_at'][:16]}"
                       f"  所要: {state.get('elapsed_min','?')}分")

        return (f"Status  : {state['status']}\n"
                f"Progress: {done}/{total} ({pct:.1f}%){eta_str}\n"
                f"PASS    : {state['passed']}  Errors: {state['errors']}\n"
                f"Last    : {state['last_code']}{fin_str}")

    # Fallback to file
    prog    = _load_progress()
    results = _load_results()
    idx     = prog.get("last_index", 0)
    total   = prog.get("total", 0)
    if total == 0:
        return "No screen_full run found. Call screen_full() to start."

    pct         = idx / total * 100 if total else 0
    meta        = results.get("__meta__", {})
    pass_count  = meta.get("passed", sum(
        1 for k, v in results.items() if k != "__meta__" and v.get("passed")))
    elapsed_min = meta.get("elapsed_min")
    el_str      = f"\n  所要時間: {elapsed_min}分" if elapsed_min else ""
    status      = "complete" if idx >= total else "paused"

    return (f"Status  : {status} (file)\n"
            f"Progress: {idx}/{total} ({pct:.1f}%){el_str}\n"
            f"PASS    : {pass_count}  Results: {RESULTS_FILE}")


@mcp.tool()
def screen_full_results(
    min_score:   int  = 6,
    top_n:       int  = 50,
    near_high:   bool = False,
    exclude_etf: bool = True,
    sort_by:     str  = "score",
) -> str:
    """
    Query results from the last screen_full run.
    min_score  : minimum Minervini score (default 6).
    top_n      : rows to return (default 50).
    near_high  : True = only stocks within 5% of 52w high (高値更新圏).
    exclude_etf: exclude ETF/REIT (default True).
    sort_by    : "score" | "rs10w" | "rs30w" | "rs50w" | "price" | "high_pct"
    """
    results = _load_results()
    if not results:
        return "No results. Run screen_full() first."

    meta     = results.get("__meta__", {})
    meta_str = ""
    if meta:
        meta_str = (f"[前回実行: {meta.get('started_at','')[:16]}  "
                    f"所要: {meta.get('elapsed_min','?')}分  "
                    f"対象: {meta.get('total','?')}銘柄  "
                    f"PASS: {meta.get('passed','?')}]\n\n")

    filtered = []
    for k, v in results.items():
        if k == "__meta__" or v.get("error"):
            continue
        score = int(v.get("score", "0/7").split("/")[0])
        if score < min_score:
            continue
        if exclude_etf and _is_etf(v.get("code", "")):
            continue
        if near_high:
            price  = v.get("price", 0)
            high52 = v.get("high52", 0)
            if high52 <= 0 or price < high52 * 0.95:
                continue
        filtered.append((score, v))

    # Sort
    if sort_by in ("rs10w", "rs30w", "rs50w", "rs26w"):
        key = {"rs10w": "rs10w", "rs30w": "rs30w",
               "rs50w": "rs50w", "rs26w": "rs50w"}.get(sort_by, "rs50w")
        filtered.sort(key=lambda x: -(x[1].get(key) or 0))
    elif sort_by == "price":
        filtered.sort(key=lambda x: -x[1].get("price", 0))
    elif sort_by == "high_pct":
        def _hp(v):
            p, h = v.get("price", 0), v.get("high52", 0)
            return -(p / h) if h else 0
        filtered.sort(key=lambda x: _hp(x[1]))
    else:
        filtered.sort(key=lambda x: -x[0])

    if not filtered:
        label = " (near 52w high)" if near_high else ""
        return f"No stocks with score >= {min_score}/7{label}."

    header = (f"  {'Code':<6}  {'Name':<22}  {'Sc':<4}  "
              f"{'Price':>9}  {'52wH':>9}  {'高値%':>6}  "
              f"{'RS10w':>7}  {'RS50w':>7}\n"
              f"  {'-'*82}\n")
    rows = []
    for _, r in filtered[:top_n]:
        price   = r.get("price", 0)
        high52  = r.get("high52", 0)
        hp      = f"{price/high52*100:.1f}%" if high52 else "  N/A"
        rs10    = f"{r['rs10w']:.3f}"  if r.get("rs10w")  is not None else "  N/A"
        rs50    = f"{r['rs50w']:.3f}"  if r.get("rs50w")  is not None else "  N/A"
        rows.append(
            f"  {r['code']:<6}  {r.get('name','')[:22]:<22}  {r['score']:<4}  "
            f"¥{price:>8,.0f}  ¥{high52:>8,.0f}  {hp:>6}  {rs10:>7}  {rs50:>7}"
        )

    label    = " 高値更新圏" if near_high else ""
    etf_note = " ETF除外" if exclude_etf else ""
    return (f"{meta_str}"
            f"≥{min_score}/7{label}{etf_note}  sort:{sort_by}  "
            f"({min(top_n, len(filtered))}/{len(filtered)}件)\n\n"
            f"{header}" + "\n".join(rows))

# ── 3. 業績データ ────────────────────────────────────────────
# mcp_server パッケージからのツール登録（@mcp.tool デコレータ発火用 import）
# ---------------------------------------------------------------------------
import mcp_server.patterns    # noqa: F401, E402
import mcp_server.fins_tools  # noqa: F401, E402
import mcp_server.portfolio   # noqa: F401, E402
import mcp_server.watchlist   # noqa: F401, E402
import mcp_server.charts      # noqa: F401, E402
import mcp_server.exports     # noqa: F401, E402
import mcp_server.utils       # noqa: F401, E402


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run()
