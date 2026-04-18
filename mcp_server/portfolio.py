"""ポートフォリオ管理 MCP tool 群。

保有銘柄の追加・削除・表示・損益計算。
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from mcp_server._context import mcp, PORTFOLIO_FILE, BASE_DIR


def _lookup_name(code_4: str) -> str:
    from stock_mcp_server import _lookup_name as _impl
    return _impl(code_4)


def _load_portfolio() -> dict:
    if PORTFOLIO_FILE.exists():
        return json.loads(PORTFOLIO_FILE.read_text(encoding="utf-8"))
    return {}

def _save_portfolio(p: dict):
    PORTFOLIO_FILE.write_text(
        json.dumps(p, ensure_ascii=False, indent=2), encoding="utf-8"
    )

@mcp.tool()
def portfolio_add(code: str, shares: float, cost: float) -> str:
    """
    Add or update a holding.
    code  : stock code (e.g. "6758")
    shares: number of shares held
    cost  : average purchase price per share (JPY)
    Example: portfolio_add("6758", 100, 3200)
    """
    p    = _load_portfolio()
    name = _lookup_name(code)
    # キャッシュになければAPI取得を試みる
    if not name:
        try:
            fetch_equity_master()
            name = _lookup_name(code)
        except Exception:
            pass
    p[code] = {
        "code":     code,
        "name":     name,
        "shares":   shares,
        "cost":     cost,
        "added_at": datetime.now().isoformat(),
    }
    _save_portfolio(p)
    return f"Portfolio updated: {code} {name}  {shares}株 @ ¥{cost:,.0f}"


@mcp.tool()
def portfolio_remove(code: str) -> str:
    """Remove a stock from portfolio. Example: portfolio_remove("6758")"""
    p = _load_portfolio()
    if code not in p:
        return f"{code} is not in portfolio."
    del p[code]
    _save_portfolio(p)
    return f"Removed {code} from portfolio."


@mcp.tool()
def portfolio_show() -> str:
    """
    Show portfolio with current prices and P&L.
    Fetches latest price from saved daily CSV (no API call).
    """
    p = _load_portfolio()
    if not p:
        return "Portfolio is empty. Use portfolio_add() to add holdings."

    total_cost  = 0.0
    total_value = 0.0
    lines = [f"  {'Code':<6}  {'Name':<20}  {'株数':>6}  "
             f"{'取得単価':>9}  {'現在値':>9}  {'損益':>10}  {'損益率':>7}",
             f"  {'-'*75}"]

    for code, h in p.items():
        shares = h["shares"]
        cost   = h["cost"]
        # Try to read latest price from daily CSV
        csv_path = CSV_DIR / f"{code}_daily.csv"
        current  = None
        if csv_path.exists():
            try:
                df      = pd.read_csv(csv_path)
                current = float(df["close"].iloc[-1])
            except Exception:
                pass

        if current is not None:
            pnl     = (current - cost) * shares
            pnl_pct = (current / cost - 1) * 100
            total_cost  += cost * shares
            total_value += current * shares
            sign = "+" if pnl >= 0 else ""
            lines.append(
                f"  {code:<6}  {h.get('name','')[:20]:<20}  {shares:>6,.0f}  "
                f"¥{cost:>8,.0f}  ¥{current:>8,.0f}  "
                f"{sign}¥{pnl:>8,.0f}  {sign}{pnl_pct:>5.1f}%"
            )
        else:
            lines.append(
                f"  {code:<6}  {h.get('name','')[:20]:<20}  {shares:>6,.0f}  "
                f"¥{cost:>8,.0f}  (価格未取得)"
            )

    if total_cost > 0:
        total_pnl     = total_value - total_cost
        total_pnl_pct = (total_value / total_cost - 1) * 100
        sign = "+" if total_pnl >= 0 else ""
        lines += [
            f"  {'-'*75}",
            f"  {'合計':<28}  評価額: ¥{total_value:>12,.0f}  "
            f"損益: {sign}¥{total_pnl:>10,.0f}  ({sign}{total_pnl_pct:.1f}%)"
        ]

    return "\n".join(lines)

# ── 5. ウォッチリスト管理 ─────────────────────────────────────

