"""MCP サーバー共通 context: FastMCP インスタンス・パス定数・並列ジョブ状態。

`mcp` は全モジュール共通の singleton。各モジュールは
`from mcp_server._context import mcp` してから `@mcp.tool()` する。
"""
from __future__ import annotations

import os
import threading
from pathlib import Path

from mcp.server.fastmcp import FastMCP

try:
    import yfinance as yf
    _YF_AVAILABLE = True
except ImportError:
    yf = None  # type: ignore[assignment]
    _YF_AVAILABLE = False


# ─── FastMCP インスタンス（全モジュールで共有） ────────────────────
mcp = FastMCP("stock-analyzer")


# ─── パス定数 ──────────────────────────────────────────────────
_DEFAULT_BASE = r"C:\Users\yohei\Documents\invest-system-github"
BASE_DIR   = Path(os.environ.get("INVEST_BASE_DIR", _DEFAULT_BASE))
DB_PATH    = BASE_DIR / "data" / "stock_prices.db"
CSV_DIR    = BASE_DIR / "csv_output"
CONFIG     = Path.home() / ".jquants_config.json"

PROGRESS_FILE  = BASE_DIR / "data" / "screen_full_progress.json"
RESULTS_FILE   = BASE_DIR / "data" / "screen_full_results.json"
MASTER_CACHE   = BASE_DIR / "data" / "equity_master_cache.json"
PORTFOLIO_FILE = BASE_DIR / "data" / "portfolio.json"
WATCHLIST_FILE = BASE_DIR / "data" / "watchlist.json"

_DEFAULT_GITHUB = r"C:\Users\yohei\Documents\invest-system-github"
GITHUB_DIR  = Path(os.environ.get("INVEST_GITHUB_DIR", _DEFAULT_GITHUB))
CHART_DIR   = GITHUB_DIR / "charts"


# ─── 稼働パラメータ ─────────────────────────────────────────────
MASTER_CACHE_TTL_DAYS = 7
BATCH_SIZE        = 50
BATCH_SLEEP_SEC   = 0.5
REQUEST_SLEEP_SEC = 0.1
MAX_RETRIES       = 3
RETRY_SLEEP_SEC   = 10.0
PARALLEL_WORKERS  = 5   # 並列APIリクエスト数（有料プラン向け）

# Nikkei225 ETF code used as benchmark for RS calculation
NIKKEI225_CODE = "1321"

# ETF / investment trust code prefixes (13xx - 19xx)
ETF_CODE_PREFIXES = ("13", "14", "15", "16", "17", "18", "19")

# Major stocks for screen_all
MAJOR_STOCKS = [
    "7203", "6758", "9984", "6861", "7974",
    "8306", "9433", "6954", "4502", "8035",
    "6367", "9432", "7267", "6501", "4063",
    "8411", "6702", "9022", "4568", "3382",
]


# ─── 背景ジョブ共有状態（bulk_download 進捗追跡） ──────────────────
_job_lock  = threading.Lock()
_job_state = {
    "running":     False,
    "done":        0,
    "total":       0,
    "passed":      0,
    "errors":      0,
    "started_at":  None,
    "finished_at": None,
    "elapsed_min": None,
    "status":      "idle",
    "last_code":   "",
}
