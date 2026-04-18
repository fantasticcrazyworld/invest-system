"""一括ダウンロード MCP tool 群 (株価日足 + 財務諸表)。

背景スレッドで J-Quants API を並列叩いて、全上場銘柄の日足・財務データを DB に蓄積する。
進捗は `_job_state` でリアルタイム追跡可能。
"""
from __future__ import annotations

import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import pandas as pd
import requests

from mcp_server._api import _headers
from mcp_server._context import (
    mcp, BASE_DIR, DB_PATH, BATCH_SIZE, BATCH_SLEEP_SEC, REQUEST_SLEEP_SEC,
    MAX_RETRIES, RETRY_SLEEP_SEC, PARALLEL_WORKERS,
    _job_lock, _job_state,
)
from mcp_server._db import _save_daily_db, _save_weekly
from mcp_server._fetch import _fetch_daily, _fetch_daily_yf, _daily_to_weekly
from mcp_server.equity import fetch_equity_master, _is_etf


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
