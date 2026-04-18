"""監視銘柄 MCP tool 群。"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from mcp_server._context import mcp, WATCHLIST_FILE, BASE_DIR


def _lookup_name(code_4: str) -> str:
    from stock_mcp_server import _lookup_name as _impl
    return _impl(code_4)


def _load_watchlist() -> dict:
    if WATCHLIST_FILE.exists():
        return json.loads(WATCHLIST_FILE.read_text(encoding="utf-8"))
    return {}

def _save_watchlist(w: dict):
    WATCHLIST_FILE.write_text(
        json.dumps(w, ensure_ascii=False, indent=2), encoding="utf-8"
    )

@mcp.tool()
def watchlist_add(code: str, memo: str = "") -> str:
    """
    Add a stock to watchlist with optional memo.
    Example: watchlist_add("6758", "高値ブレイクアウト待ち")
    """
    w    = _load_watchlist()
    name = _lookup_name(code)
    if not name:
        try:
            fetch_equity_master()
            name = _lookup_name(code)
        except Exception:
            pass
    w[code] = {
        "code":     code,
        "name":     name,
        "memo":     memo,
        "added_at": datetime.now().isoformat(),
    }
    _save_watchlist(w)
    return f"Watchlist追加: {code} {name}  memo: {memo}"


@mcp.tool()
def watchlist_remove(code: str) -> str:
    """Remove a stock from watchlist. Example: watchlist_remove("6758")"""
    w = _load_watchlist()
    if code not in w:
        return f"{code} is not in watchlist."
    del w[code]
    _save_watchlist(w)
    return f"Removed {code} from watchlist."


@mcp.tool()
def watchlist_show() -> str:
    """
    Show watchlist with current Minervini score and price.
    Reads from saved daily CSV (no API call).
    """
    w = _load_watchlist()
    if not w:
        return "Watchlist is empty. Use watchlist_add() to add stocks."

    lines = [f"  {'Code':<6}  {'Name':<22}  {'Score':<5}  "
             f"{'Price':>9}  {'52wH':>9}  {'高値%':>6}  Memo",
             f"  {'-'*75}"]

    for code, item in w.items():
        csv_path = CSV_DIR / f"{code}_daily.csv"
        score_str = "N/A"
        price_str = "N/A"
        high_str  = "N/A"
        hp_str    = "N/A"

        if csv_path.exists():
            try:
                df     = pd.read_csv(csv_path, parse_dates=["date"]).set_index("date")
                result = _minervini(df)
                if "error" not in result:
                    price  = result["price"]
                    high52 = result["high52"]
                    score_str = result["score"]
                    price_str = f"¥{price:>8,.0f}"
                    high_str  = f"¥{high52:>8,.0f}"
                    hp_str    = f"{price/high52*100:.1f}%" if high52 else "N/A"
            except Exception:
                pass

        lines.append(
            f"  {code:<6}  {item.get('name','')[:22]:<22}  {score_str:<5}  "
            f"{price_str:>9}  {high_str:>9}  {hp_str:>6}  {item.get('memo','')}"
        )

    return "\n".join(lines)


@mcp.tool()
def watchlist_screen() -> str:
    """
    Run Minervini screening on all watchlist stocks and update prices via API.
    Example: watchlist_screen()
    """
    w = _load_watchlist()
    if not w:
        return "Watchlist is empty."

    lines = [f"Watchlist screening ({len(w)} stocks)\n",
             f"  {'Code':<6}  {'Name':<22}  {'Score':<5}  "
             f"{'Price':>9}  {'52wH':>9}  {'高値%':>6}",
             f"  {'-'*65}"]

    for code in w:
        try:
            bars   = _fetch_daily(code)
            df     = _daily_to_df(bars)
            result = _minervini(df)
            if "error" not in result:
                price  = result["price"]
                high52 = result["high52"]
                hp     = f"{price/high52*100:.1f}%" if high52 else "N/A"
                status = "PASS" if result["passed"] else "----"
                lines.append(
                    f"  {code:<6}  {w[code].get('name','')[:22]:<22}  "
                    f"{result['score']:<5}  ¥{price:>8,.0f}  "
                    f"¥{high52:>8,.0f}  {hp:>6}  {status}"
                )
                # Save latest data
                _init_db()
                _save_weekly(code, _daily_to_weekly(bars))
                _daily_to_df(bars).reset_index().to_csv(
                    CSV_DIR / f"{code}_daily.csv", index=False
                )
            time.sleep(REQUEST_SLEEP_SEC)
        except Exception as e:
            lines.append(f"  {code:<6}  ERROR: {e}")

    return "\n".join(lines)

# ---------------------------------------------------------------------------
# Chart generation (Plotly candlestick)
# ---------------------------------------------------------------------------

