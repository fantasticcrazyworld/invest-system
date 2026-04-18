"""ミネルヴィニのトレンドテンプレート 7 条件スコア + RS 計算。"""
from __future__ import annotations

import pandas as pd


def _minervini(daily_df: pd.DataFrame) -> dict:
    c = daily_df["close"].values.astype(float)
    if len(c) < 52:
        return {"error": f"only {len(c)} trading days (need >= 52)"}

    price     = c[-1]
    sma50     = c[-min(50,  len(c)):].mean()
    sma150    = c[-min(150, len(c)):].mean()
    sma200    = c[-min(200, len(c)):].mean()
    sma200_1m = c[-min(220, len(c)):-20].mean() if len(c) >= 30 else sma200 * 0.999
    high52    = c[-min(252, len(c)):].max()
    low52     = c[-min(252, len(c)):].min()

    cond = [
        bool(price > sma150 and price > sma200),   # 1
        bool(sma150 > sma200),                      # 2
        bool(sma200 > sma200_1m),                   # 3
        bool(sma50 > sma150 and sma50 > sma200),   # 4
        bool(price > sma50),                        # 5
        bool(price > low52 * 1.25),                 # 6
        bool(price > high52 * 0.75),                # 7
    ]
    n = sum(cond)
    return {
        "passed":     n >= 6,
        "score":      f"{n}/7",
        "conditions": cond,
        "price":      round(float(price), 1),
        "sma50":      round(float(sma50), 1),
        "sma150":     round(float(sma150), 1),
        "sma200":     round(float(sma200), 1),
        "high52":     round(float(high52), 1),
        "low52":      round(float(low52), 1),
        "days":       len(c),
    }

# ---------------------------------------------------------------------------
# RS (Relative Strength) vs Nikkei225
# ---------------------------------------------------------------------------

def _calc_rs(stock_weekly_closes: list, bench_weekly_closes: list) -> dict:
    """
    週足ベースのRelative Strength計算。
    日足50/150/250本を週足に換算: n=10w/30w/50w
      10週 ≈ 50日(2.5ヶ月)
      30週 ≈ 150日(6ヶ月)
      50週 ≈ 250日(1年)
    計算式: (1 + stock_return) / (1 + bench_return)
      RS > 1.0 = アウトパフォーム
      RS < 1.0 = アンダーパフォーム
    旧式 stock_return/bench_return は下落相場で符号が反転するバグあり → 修正済み
    """
    def _rs(stock, bench, n):
        if len(stock) < n + 1 or len(bench) < n + 1:
            return None
        sr = stock[-1] / stock[-n - 1] - 1.0
        br = bench[-1] / bench[-n - 1] - 1.0
        if br == -1.0:
            return None
        return round((1.0 + sr) / (1.0 + br), 3)

    s = stock_weekly_closes
    b = bench_weekly_closes

    return {
        "rs10w":  _rs(s, b, 10),  # ≈50日(2.5ヶ月)
        "rs30w":  _rs(s, b, 30),  # ≈150日(6ヶ月)
        "rs50w":  _rs(s, b, 50),  # ≈250日(1年)
    }

# ---------------------------------------------------------------------------
# Fundamental data
# ---------------------------------------------------------------------------

