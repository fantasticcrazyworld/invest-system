"""チャート生成 MCP tool 群。

`_load_daily_csv` は他モジュール (patterns.py, exports.py) からも参照される共通関数。
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from mcp_server._context import mcp, BASE_DIR, CSV_DIR, CHART_DIR, GITHUB_DIR


def _lookup_name(code_4: str) -> str:
    from stock_mcp_server import _lookup_name as _impl
    return _impl(code_4)


def _detect_all_patterns(df: pd.DataFrame) -> dict:
    from mcp_server.patterns import _detect_all_patterns as _impl
    return _impl(df)


def _load_daily_csv(code: str) -> pd.DataFrame:
    """Load daily data: DB (historical) + CSV (latest), merged and deduplicated."""
    frames = []

    # 1. Load from DB (long history)
    db_df = _load_daily_db(code)
    if not db_df.empty:
        frames.append(db_df)

    # 2. Load from CSV (latest ~400 days)
    csv_path = CSV_DIR / f"{code}_daily.csv"
    if csv_path.exists():
        try:
            csv_df = pd.read_csv(csv_path, parse_dates=["date"])
            csv_df = csv_df.sort_values("date").set_index("date")
            frames.append(csv_df)
        except Exception:
            pass

    if not frames:
        return pd.DataFrame()

    # Merge: concat and deduplicate (keep latest data for overlapping dates)
    df = pd.concat(frames)
    df = df[~df.index.duplicated(keep="last")]
    df = df.sort_index()
    return df


@mcp.tool()
def generate_chart(code: str, show_patterns: bool = True) -> str:
    """ローソク足チャートを生成してブラウザで表示する。

    SMA50/150/200、出来高、52週高値/安値ラインを含む本格的なチャート。
    show_patterns=True の場合、検出されたパターンもチャート上に表示。

    Args:
        code: 4桁銘柄コード
        show_patterns: パターン検出結果をチャートに重ねるか
    """
    # Load data (CSV first, fallback to API)
    df = _load_daily_csv(code)
    if df.empty:
        try:
            bars = _fetch_daily(code)
            if not bars:
                return f"ERROR: No price data for {code}"
            df = _daily_to_df(bars)
            # Save CSV for future use
            df.reset_index().to_csv(CSV_DIR / f"{code}_daily.csv", index=False)
        except Exception as e:
            return f"ERROR fetching data: {e}"

    if len(df) < 50:
        return f"ERROR: Only {len(df)} days of data (need >= 50)"

    c = df["close"].values.astype(float)
    sma50  = pd.Series(c).rolling(50).mean()
    sma150 = pd.Series(c).rolling(150).mean()
    sma200 = pd.Series(c).rolling(200).mean()
    high52 = pd.Series(c).rolling(min(252, len(c))).max()
    low52  = pd.Series(c).rolling(min(252, len(c))).min()

    dates = df.index

    # Create subplots: candlestick + volume
    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=[0.75, 0.25],
    )

    # Candlestick
    fig.add_trace(go.Candlestick(
        x=dates, open=df["open"], high=df["high"],
        low=df["low"], close=df["close"], name="OHLC",
        increasing_line_color="#26a69a", decreasing_line_color="#ef5350",
    ), row=1, col=1)

    # SMAs
    for sma, name, color in [
        (sma50,  "SMA50",  "#2196F3"),
        (sma150, "SMA150", "#FF9800"),
        (sma200, "SMA200", "#9C27B0"),
    ]:
        fig.add_trace(go.Scatter(
            x=dates, y=sma.values, name=name,
            line=dict(color=color, width=1.2),
        ), row=1, col=1)

    # 52-week high/low
    fig.add_trace(go.Scatter(
        x=dates, y=high52.values, name="52W High",
        line=dict(color="rgba(255,0,0,0.3)", width=1, dash="dot"),
    ), row=1, col=1)
    fig.add_trace(go.Scatter(
        x=dates, y=low52.values, name="52W Low",
        line=dict(color="rgba(0,128,0,0.3)", width=1, dash="dot"),
    ), row=1, col=1)

    # Volume bars
    colors = ["#26a69a" if df["close"].iloc[i] >= df["open"].iloc[i]
              else "#ef5350" for i in range(len(df))]
    fig.add_trace(go.Bar(
        x=dates, y=df["volume"], name="Volume",
        marker_color=colors, opacity=0.7,
    ), row=2, col=1)

    # Pattern annotations
    if show_patterns:
        try:
            patterns = _detect_all_patterns(df)
            for p_name, p_data in patterns.items():
                if p_data.get("detected"):
                    details = p_data.get("details", {})
                    pivot = details.get("pivot_price") or details.get("resistance")
                    if pivot:
                        fig.add_hline(
                            y=pivot, line_dash="dash", line_color="gold",
                            annotation_text=f"{p_name} pivot: {pivot:.0f}",
                            row=1, col=1,
                        )
        except Exception:
            pass

    fig.update_layout(
        title=f"{code} Daily Chart",
        template="plotly_dark",
        xaxis_rangeslider_visible=False,
        height=700, width=1100,
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        margin=dict(l=50, r=30, t=60, b=30),
    )
    fig.update_yaxes(title_text="Price", row=1, col=1)
    fig.update_yaxes(title_text="Volume", row=2, col=1)

    # Save & open
    CHART_DIR.mkdir(parents=True, exist_ok=True)
    html_path = CHART_DIR / f"{code}_chart.html"
    fig.write_html(str(html_path), include_plotlyjs=True)
    webbrowser.open(html_path.as_uri())

    return f"OK: Chart saved to {html_path} and opened in browser"


# ---------------------------------------------------------------------------
# Chart pattern detection
# ---------------------------------------------------------------------------

