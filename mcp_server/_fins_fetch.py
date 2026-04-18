"""J-Quants から財務諸表 (statements) を取得するヘルパー。"""
from __future__ import annotations

import time

import requests

from mcp_server._api import _headers
from mcp_server._context import REQUEST_SLEEP_SEC, MAX_RETRIES, RETRY_SLEEP_SEC


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

