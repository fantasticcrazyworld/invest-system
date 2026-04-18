"""銘柄マスタ (JPX 上場銘柄一覧) の取得・名称引き + MCP tool。

`get_equity_master` は MCP ツールとして公開され、手動キャッシュ更新に使う。
"""
from __future__ import annotations

import json
import time
from datetime import datetime

import requests

from mcp_server._api import _headers
from mcp_server._context import (
    mcp, MASTER_CACHE, MASTER_CACHE_TTL_DAYS, ETF_CODE_PREFIXES,
)


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

