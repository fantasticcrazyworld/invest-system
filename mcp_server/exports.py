"""各種データエクスポート MCP tool 群。

chart_data / fins_data / timeline_data / pattern_data など、
サイト (`index.html`) が fetch する JSON を生成する。
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd

from mcp_server._context import (
    mcp, BASE_DIR, CSV_DIR, GITHUB_DIR, RESULTS_FILE,
)


def _load_daily_csv(code):
    from mcp_server.charts import _load_daily_csv as _impl
    return _impl(code)


def _fetch_daily(code_4: str, days: int = 2000) -> list:
    from stock_mcp_server import _fetch_daily as _impl
    return _impl(code_4, days)


def _daily_to_df(bars: list):
    from stock_mcp_server import _daily_to_df as _impl
    return _impl(bars)


def _minervini(df):
    from stock_mcp_server import _minervini as _impl
    return _impl(df)


def _fetch_fins_history(code_4: str) -> list:
    from stock_mcp_server import _fetch_fins_history as _impl
    return _impl(code_4)


def _lookup_name(code_4: str) -> str:
    from stock_mcp_server import _lookup_name as _impl
    return _impl(code_4)


def _detect_all_patterns(df):
    from mcp_server.patterns import _detect_all_patterns as _impl
    return _impl(df)


def _export_one(code: str, df: pd.DataFrame, max_days: int,
                chart_data: dict, pattern_data: dict,
                timeline_data: dict = None):
    """Export chart + pattern data for a single stock."""
    df_clean = df.dropna(subset=["open", "high", "low", "close"]).tail(max_days)
    records = []
    for date, row in df_clean.iterrows():
        records.append({
            "time": date.strftime("%Y-%m-%d"),
            "open": round(float(row["open"]), 1),
            "high": round(float(row["high"]), 1),
            "low": round(float(row["low"]), 1),
            "close": round(float(row["close"]), 1),
            "volume": int(row["volume"]) if pd.notna(row["volume"]) else 0,
        })
    chart_data[code] = records

    patterns = _detect_all_patterns(df)
    detected = [k for k, v in patterns.items() if v.get("detected")]
    if detected:
        pattern_data[code] = {
            "patterns": detected,
            "details": {k: v for k, v in patterns.items() if v.get("detected")},
        }

    # Timeline: YTD high date, 52-week high date
    if timeline_data is not None:
        closes = df["close"].dropna()
        tl = {}
        # YTD high date
        try:
            ytd_start = f"{datetime.now().year}-01-01"
            ytd_df = closes[closes.index >= ytd_start]
            if not ytd_df.empty:
                ytd_high_date = ytd_df.idxmax()
                tl["ytd_high_date"] = ytd_high_date.strftime("%Y-%m-%d")
                tl["ytd_high_price"] = round(float(ytd_df.max()), 1)
        except Exception:
            pass
        # 52-week high date
        try:
            w52 = closes.tail(252)
            if not w52.empty:
                high52_date = w52.idxmax()
                tl["high52_date"] = high52_date.strftime("%Y-%m-%d")
                tl["high52_price"] = round(float(w52.max()), 1)
        except Exception:
            pass
        if tl:
            timeline_data[code] = tl


def _ensure_csv(code: str) -> pd.DataFrame:
    """Load data or fetch from API. Saves to both CSV and DB."""
    df = _load_daily_csv(code)
    if not df.empty:
        return df
    try:
        bars = _fetch_daily(code)
        if not bars:
            return pd.DataFrame()
        df = _daily_to_df(bars)
        CSV_DIR.mkdir(parents=True, exist_ok=True)
        df.reset_index().to_csv(CSV_DIR / f"{code}_daily.csv", index=False)
        _save_daily_db(code, df)  # Persist to DB for long-term storage
        time.sleep(REQUEST_SLEEP_SEC)
        return df
    except Exception:
        return pd.DataFrame()


@mcp.tool()
def export_chart_data(extra_codes: str = "", max_days: int = 200,
                      ytd_near_pct: float = 0.98) -> str:
    """サイト用チャート・パターンデータをエクスポートする。

    対象銘柄（自動選定）:
    1. 監視銘柄リスト（watchlist.json）の全銘柄 → 必ず含む
    2. ポートフォリオ（portfolio.json）の全銘柄 → 必ず含む
    3. 年初来高値更新圏（price >= ytd_high * ytd_near_pct）のPASS銘柄

    Args:
        extra_codes: カンマ区切りで追加銘柄コード（例: "7203,6758"）
        max_days: チャート日数（デフォルト200）
        ytd_near_pct: 年初来高値の何%以内を対象にするか（デフォルト0.98）
    """
    # Try invest-data (site version) first, fallback to local
    data = None
    _INVEST_DATA_URL = (
        "https://raw.githubusercontent.com/"
        "yangpinggaoye15-dotcom/invest-data/main/screen_full_results.json"
    )
    try:
        resp = requests.get(_INVEST_DATA_URL, timeout=15)
        if resp.ok:
            data = resp.json()
    except Exception:
        pass
    if data is None:
        if not RESULTS_FILE.exists():
            return "ERROR: screen_full results not found."
        data = json.loads(RESULTS_FILE.read_text(encoding="utf-8"))

    items_dict = data if isinstance(data, dict) else {}
    if isinstance(data, list):
        items_dict = {i.get("code", ""): i for i in data if isinstance(i, dict)}

    # 1. Watchlist codes (always included)
    watchlist = _load_watchlist()
    wl_codes = set(watchlist.keys())

    # 2. Portfolio codes (always included)
    portfolio = _load_portfolio()
    pf_codes = set(portfolio.keys())

    # 3. YTD high stocks (PASS with price near ytd_high)
    ytd_codes = set()
    for code, item in items_dict.items():
        if code == "__meta__" or not isinstance(item, dict):
            continue
        if not item.get("passed"):
            continue
        ytd_high = item.get("ytd_high")
        price = item.get("price", 0)
        if ytd_high and price >= ytd_high * ytd_near_pct:
            ytd_codes.add(code)

    # 4. Extra codes from argument
    extra = set()
    if extra_codes:
        extra = {c.strip() for c in extra_codes.split(",") if c.strip()}

    target_codes = wl_codes | pf_codes | ytd_codes | extra
    if not target_codes:
        return "No target stocks found (no watchlist, portfolio, or YTD-high stocks)"

    chart_data = {}
    pattern_data = {}
    timeline_data = {}
    api_fetched = 0

    for code in sorted(target_codes):
        df = _load_daily_csv(code)
        if df.empty:
            df = _ensure_csv(code)
            if not df.empty:
                api_fetched += 1
        if df.empty:
            continue
        _export_one(code, df, max_days, chart_data, pattern_data,
                    timeline_data)

    # Save chart data
    chart_path = GITHUB_DIR / "chart_data.json"
    chart_path.write_text(
        json.dumps(chart_data, ensure_ascii=False), encoding="utf-8"
    )

    # Save pattern data
    pat_path = GITHUB_DIR / "pattern_data.json"
    pat_path.write_text(
        json.dumps(pattern_data, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # Save timeline data (YTD high dates, 52w high dates)
    tl_path = GITHUB_DIR / "timeline_data.json"
    tl_path.write_text(
        json.dumps(timeline_data, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    sz = chart_path.stat().st_size // 1024
    return (
        f"OK: Exported {len(chart_data)} stocks (API fetched: {api_fetched})\n"
        f"  Watchlist: {len(wl_codes)}, Portfolio: {len(pf_codes)}, "
        f"YTD-high: {len(ytd_codes)}, Extra: {len(extra)}\n"
        f"  Chart data: {chart_path} ({sz} KB)\n"
        f"  Pattern data: {pat_path} (patterns: {len(pattern_data)})\n"
        f"  Timeline data: {tl_path} ({len(timeline_data)} stocks)\n"
        f"Push to invest-data repo to update the site."
    )


@mcp.tool()
def export_site_data() -> str:
    """watchlist.jsonとportfolio.jsonをGitHubリポジトリにコピーする。

    invest-dataにpushすればサイトで監視銘柄リスト・ポートフォリオが表示される。
    """
    copied = []
    for src_path, name in [
        (WATCHLIST_FILE, "watchlist.json"),
        (PORTFOLIO_FILE, "portfolio.json"),
    ]:
        dst = GITHUB_DIR / name
        if src_path.exists():
            content = src_path.read_text(encoding="utf-8")
            dst.write_text(content, encoding="utf-8")
            copied.append(f"  {name}: {dst}")
        else:
            # Write empty JSON
            dst.write_text("{}", encoding="utf-8")
            copied.append(f"  {name}: (empty) {dst}")

    return "OK: Copied to GITHUB_DIR\n" + "\n".join(copied)


KNOWLEDGE_DIR = GITHUB_DIR / "knowledge"


@mcp.tool()
def save_knowledge(code: str, text: str, category: str = "general") -> str:
    """銘柄のナレッジ（学習事項）をファイルに保存する。

    AIへの質問時に過去ナレッジとして参照される。

    Args:
        code: 4桁銘柄コード
        text: ナレッジ内容
        category: カテゴリ（general/news/plan/analysis/backtest）
    """
    KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
    kl_path = KNOWLEDGE_DIR / f"{code}.json"
    entries = []
    if kl_path.exists():
        try:
            entries = json.loads(kl_path.read_text(encoding="utf-8"))
        except Exception:
            entries = []

    entries.insert(0, {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "category": category,
        "text": text[:1000],
    })
    # Keep max 20 per stock
    entries = entries[:20]

    kl_path.write_text(
        json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return f"OK: Knowledge saved for {code} ({len(entries)} entries)"


@mcp.tool()
def export_knowledge() -> str:
    """ナレッジデータをサイト用にエクスポートする。

    knowledge/*.json を1つの knowledge_data.json にまとめる。
    invest-dataにpushすればAI質問時に参照される。
    """
    KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
    all_kl = {}
    for kl_file in KNOWLEDGE_DIR.glob("*.json"):
        code = kl_file.stem
        try:
            entries = json.loads(kl_file.read_text(encoding="utf-8"))
            if entries:
                all_kl[code] = entries
        except Exception:
            pass

    kl_path = GITHUB_DIR / "knowledge_data.json"
    kl_path.write_text(
        json.dumps(all_kl, ensure_ascii=False), encoding="utf-8"
    )
    return f"OK: Exported knowledge for {len(all_kl)} stocks to {kl_path}"


@mcp.tool()
def export_fins_data(extra_codes: str = "", ytd_near_pct: float = 0.98) -> str:
    """年初来高値圏+監視+ポートフォリオ銘柄の業績データをJSONエクスポートする。

    J-Quants APIから過去5年分の業績（通期+四半期+予想）を取得。
    invest-dataにpushすればサイトの業績ページに反映。

    Args:
        extra_codes: カンマ区切りで追加銘柄コード
        ytd_near_pct: 年初来高値の何%以内を対象にするか（デフォルト0.98）
    """
    # Try invest-data (site version) first, fallback to local
    data = None
    _INVEST_DATA_URL = (
        "https://raw.githubusercontent.com/"
        "yangpinggaoye15-dotcom/invest-data/main/screen_full_results.json"
    )
    try:
        resp = requests.get(_INVEST_DATA_URL, timeout=15)
        if resp.ok:
            data = resp.json()
    except Exception:
        pass
    if data is None:
        if not RESULTS_FILE.exists():
            return "ERROR: screen_full results not found."
        data = json.loads(RESULTS_FILE.read_text(encoding="utf-8"))

    items_dict = data if isinstance(data, dict) else {}

    # Target stocks (same logic as export_chart_data)
    watchlist = _load_watchlist()
    portfolio = _load_portfolio()
    wl_codes = set(watchlist.keys())
    pf_codes = set(portfolio.keys())

    ytd_codes = set()
    for code, item in items_dict.items():
        if code == "__meta__" or not isinstance(item, dict):
            continue
        if not item.get("passed"):
            continue
        ytd_high = item.get("ytd_high")
        price = item.get("price", 0)
        if ytd_high and price >= ytd_high * ytd_near_pct:
            ytd_codes.add(code)

    extra = set()
    if extra_codes:
        extra = {c.strip() for c in extra_codes.split(",") if c.strip()}

    target_codes = wl_codes | pf_codes | ytd_codes | extra
    if not target_codes:
        return "No target stocks found"

    fins_data = {}
    fetched = 0
    errors = 0

    for code in sorted(target_codes):
        try:
            records = _fetch_fins_history(code)
            if records:
                fins_data[code] = records
                fetched += 1
            time.sleep(REQUEST_SLEEP_SEC)
        except Exception:
            errors += 1

    # Save
    fins_path = GITHUB_DIR / "fins_data.json"
    fins_path.write_text(
        json.dumps(fins_data, ensure_ascii=False), encoding="utf-8"
    )

    sz = fins_path.stat().st_size // 1024
    return (
        f"OK: Fetched financials for {fetched} stocks (errors: {errors})\n"
        f"  Target: WL={len(wl_codes)}, PF={len(pf_codes)}, "
        f"YTD={len(ytd_codes)}, Extra={len(extra)}\n"
        f"  Saved: {fins_path} ({sz} KB)"
    )


# ---------------------------------------------------------------------------
# General-purpose file & command tools
# ---------------------------------------------------------------------------
