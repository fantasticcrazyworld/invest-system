"""財務データ MCP tool 群。

get_fins (J-Quants API から取得) と debug_fins_raw (生データ確認用)。
内部の _fetch_fins / _fetch_fins_history / _headers は stock_mcp_server.py に残存。
"""
from __future__ import annotations

import json

from mcp_server._context import mcp


def _fetch_fins(code_4: str) -> dict:
    from stock_mcp_server import _fetch_fins as _impl
    return _impl(code_4)


def _fetch_fins_history(code_4: str) -> list:
    from stock_mcp_server import _fetch_fins_history as _impl
    return _impl(code_4)


def _lookup_name(code_4: str) -> str:
    from stock_mcp_server import _lookup_name as _impl
    return _impl(code_4)


def _headers() -> dict:
    from stock_mcp_server import _headers as _impl
    return _impl()



@mcp.tool()
def get_fins(code: str) -> str:
    """
    Fetch financial summary for a stock (sales / op-profit / net-profit / EPS).
    Example: get_fins("6758")
    """
    fins = _fetch_fins(code)
    if not fins:
        return f"No financial data for {code}."

    def fmt_jpy(v):
        if v is None: return "N/A"
        if v >= 1_000_000_000_000: return f"¥{v/1_000_000_000_000:.2f}兆"
        if v >= 100_000_000:       return f"¥{v/100_000_000:.1f}億"
        if v >= 1_000_000:         return f"¥{v/1_000_000:.1f}百万"
        return f"¥{v:,.0f}"

    def fmt(v):
        if v is None: return "N/A"
        if isinstance(v, float): return f"{v:.2f}"
        return str(v)

    name = _lookup_name(code)
    eq_ratio = fins.get("equity_ratio")
    eq_str   = f"{eq_ratio*100:.1f}%" if eq_ratio else "N/A"
    return (
        f"[{code}] {name}  業績 ({fins.get('fiscal_year','')} {fins.get('period','')})\n"
        f"  開示日    : {fins.get('disclosed_date','N/A')}\n"
        f"  売上高    : {fmt_jpy(fins.get('sales'))}\n"
        f"  営業利益  : {fmt_jpy(fins.get('op_profit'))}\n"
        f"  経常利益  : {fmt_jpy(fins.get('ord_profit'))}\n"
        f"  純利益    : {fmt_jpy(fins.get('net_profit'))}\n"
        f"  EPS       : {fmt(fins.get('eps'))}\n"
        f"  BPS       : {fmt(fins.get('bps'))}\n"
        f"  配当(年)  : {fmt(fins.get('div_annual'))}\n"
        f"  純資産    : {fmt_jpy(fins.get('equity'))}\n"
        f"  総資産    : {fmt_jpy(fins.get('total_assets'))}\n"
        f"  自己資本比: {eq_str}\n"
        f"  ── 予想 ──\n"
        f"  予想売上  : {fmt_jpy(fins.get('forecast_sales'))}\n"
        f"  予想純利益: {fmt_jpy(fins.get('forecast_profit'))}\n"
        f"  予想EPS   : {fmt(fins.get('forecast_eps'))}"
    )

@mcp.tool()
def debug_fins_raw(code: str) -> str:
    """
    Debug tool: show raw API response from /v2/fins/summary.
    Use code="master" to inspect equity master cache.
    Example: debug_fins_raw("6758"), debug_fins_raw("master")
    """
    # equity masterキャッシュの確認
    if code == "master":
        if not MASTER_CACHE.exists():
            return "Master cache not found."
        cached = json.loads(MASTER_CACHE.read_text(encoding="utf-8"))
        items  = cached.get("items", [])
        if not items:
            return "Master cache empty."
        sample = items[:3]
        return (f"Total: {len(items)} stocks\n"
                f"Keys : {list(items[0].keys())}\n\n"
                f"Sample:\n{json.dumps(sample, ensure_ascii=False, indent=2)[:1000]}")

    code_5 = code + "0"
    url    = f"https://api.jquants.com/v2/fins/summary?code={code_5}"
    try:
        resp = requests.get(url, headers=_headers(), timeout=30)
        raw  = resp.json()
        keys    = list(raw.keys())
        first   = None
        for k in keys:
            v = raw[k]
            if isinstance(v, list) and v:
                first = v[-1]
                break
        return (f"Status : {resp.status_code}\n"
                f"Keys   : {keys}\n"
                f"Latest : {json.dumps(first, ensure_ascii=False, indent=2)[:800]}")
    except Exception as e:
        return f"ERROR: {e}"

# ── 4. ポートフォリオ管理 ─────────────────────────────────────

