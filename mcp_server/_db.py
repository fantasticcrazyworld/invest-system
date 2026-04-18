"""SQLite DB 操作: 日足・週足 OHLC の保存/読込。"""
from __future__ import annotations

import sqlite3
from datetime import datetime

import pandas as pd

from mcp_server._context import DB_PATH


def _init_db():
    CSV_DIR.mkdir(parents=True, exist_ok=True)
    (BASE_DIR / "data").mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.execute("""
        CREATE TABLE IF NOT EXISTS weekly_prices (
            code TEXT, date TEXT,
            open REAL, high REAL, low REAL, close REAL, volume REAL,
            PRIMARY KEY (code, date)
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS daily_prices (
            code TEXT, date TEXT,
            open REAL, high REAL, low REAL, close REAL, volume REAL,
            PRIMARY KEY (code, date)
        )
    """)
    con.commit()
    con.close()

def _save_weekly(code: str, df: pd.DataFrame):
    con = sqlite3.connect(DB_PATH)
    df_save = df.reset_index()
    df_save.columns = [c.lower() for c in df_save.columns]
    df_save["code"] = code
    df_save.to_sql("weekly_prices", con, if_exists="replace",
                   index=False, method="multi")
    con.close()

def _load_weekly(code: str) -> pd.DataFrame:
    con = sqlite3.connect(DB_PATH)
    df  = pd.read_sql(
        "SELECT * FROM weekly_prices WHERE code=? ORDER BY date",
        con, params=(code,)
    )
    con.close()
    return df


def _save_daily_db(code: str, df: pd.DataFrame):
    """Save daily OHLCV to SQLite (upsert / append, no data loss)."""
    _init_db()
    con = sqlite3.connect(DB_PATH)
    df_save = df.reset_index()
    df_save.columns = [c.lower() for c in df_save.columns]
    df_save["code"] = code
    df_save["date"] = df_save["date"].astype(str).str[:10]
    # INSERT OR REPLACE to merge new data with existing
    for _, row in df_save.iterrows():
        con.execute(
            "INSERT OR REPLACE INTO daily_prices "
            "(code, date, open, high, low, close, volume) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (row["code"], row["date"],
             row["open"], row["high"], row["low"], row["close"], row["volume"]),
        )
    con.commit()
    con.close()


def _load_daily_db(code: str) -> pd.DataFrame:
    """Load daily OHLCV from SQLite (all historical data)."""
    _init_db()
    con = sqlite3.connect(DB_PATH)
    df = pd.read_sql(
        "SELECT date, open, high, low, close, volume "
        "FROM daily_prices WHERE code=? ORDER BY date",
        con, params=(code,),
    )
    con.close()
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date")
    return df

# ---------------------------------------------------------------------------
# Fetch helpers
# ---------------------------------------------------------------------------

