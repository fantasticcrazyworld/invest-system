"""J-Quants API 認証ヘルパー。"""
from __future__ import annotations

import json
import os

from mcp_server._context import CONFIG


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

