"""スクリーニング MCP tool 群 (ミネルヴィニ 7 条件 + 全銘柄 screen_full)。

個別銘柄 / 主要銘柄 / 全銘柄の 3 モードと、背景ジョブで進捗追跡する
`screen_full_status` / `screen_full_results` を提供。
"""
from __future__ import annotations

import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests

from mcp_server._api import _headers
from mcp_server._context import (
    mcp, BASE_DIR, CSV_DIR, CHART_DIR,
    PROGRESS_FILE, RESULTS_FILE, MASTER_CACHE,
    BATCH_SIZE, BATCH_SLEEP_SEC, REQUEST_SLEEP_SEC,
    MAX_RETRIES, RETRY_SLEEP_SEC, PARALLEL_WORKERS,
    NIKKEI225_CODE, ETF_CODE_PREFIXES, MAJOR_STOCKS,
    _job_lock, _job_state,
)
from mcp_server._db import _save_daily_db, _save_weekly, _load_daily_db
from mcp_server._fetch import (
    _fetch_daily, _fetch_daily_yf, _daily_to_df, _daily_to_weekly,
)
from mcp_server._fins_fetch import _fetch_fins
from mcp_server.minervini import _minervini, _calc_rs
from mcp_server.equity import fetch_equity_master, _is_etf, _lookup_name


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
