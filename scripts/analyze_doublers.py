"""
2ヶ月で2倍以上になった銘柄の包括分析スクリプト
Data: C:/Users/yohei/Documents/invest-system/data/stock_prices.db (2020-10-19 〜 2026-04-14, 4071銘柄)

Stages (各stageはintermediate保存・再開可能):
  1. Doubler detection: rolling 42営業日で 2x events を検出 → events.parquet
  2. Trend period: 上昇開始 (local min) ・下落開始 (peak後 -20% or -15%) を特定 → events_trend.parquet
  3. Pattern classification: Breakout / Acceleration / Parabolic / Gap-up / Slow grind / V-recovery
  4. Index/financial/volume context
  5. Excel multi-sheet output

Usage:
  python analyze_doublers.py --stage 1
  python analyze_doublers.py --stage all
"""
from __future__ import annotations
import os, sys, json, sqlite3, argparse, math
from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

DB = Path(r"C:/Users/yohei/Documents/invest-system/data/stock_prices.db")
FINS_DB = Path(r"C:/Users/yohei/Documents/invest-system-github/data/fins_data.db")
EQUITY_MASTER = Path(r"C:/Users/yohei/Documents/invest-system-github/data/equity_master_cache.json")
OUT_DIR = Path(r"C:/Users/yohei/Documents/invest-system-github/reports/analysis")
CACHE_DIR = OUT_DIR / "cache"
OUT_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR.mkdir(parents=True, exist_ok=True)

WINDOW = 42          # 2ヶ月 = 約42営業日
THRESHOLD = 2.0      # 2倍
MIN_PRICE = 50       # ボロ株除外
MIN_AVG_VOLUME = 50_000  # 流動性最低ライン

# ---------- Stage 1: Doubler detection ----------
def load_master() -> dict:
    if not EQUITY_MASTER.exists():
        return {}
    m = json.load(open(EQUITY_MASTER, encoding="utf-8"))
    items = m.get("items", [])
    out = {}
    for it in items:
        # Code は時に5桁(末尾0)、4桁混在
        c = str(it.get("Code", "")).strip()
        if c.endswith("0") and len(c) == 5:
            c = c[:4]
        out[c] = {
            "name": it.get("CoName", ""),
            "name_en": it.get("CoNameEn", ""),
            "sector17": it.get("S17Nm", ""),
            "sector33": it.get("S33Nm", ""),
            "scale": it.get("ScaleCat", ""),
            "market": it.get("MktNm", ""),
        }
    return out


def detect_doublers_for_code(df: pd.DataFrame, code: str) -> list[dict]:
    """1銘柄の全期間を走査して 2x events を返す.
    重複イベント抑制: 同一 trough (start) を重複検出した場合は最大上昇を採用。
    """
    if len(df) < WINDOW + 5:
        return []
    df = df.sort_values("date").reset_index(drop=True)
    closes = df["close"].values.astype(float)
    highs = df["high"].values.astype(float)
    vols = df["volume"].values.astype(float)
    dates = df["date"].values

    # 流動性チェック: 過去全体の平均出来高
    if np.nanmean(vols) < MIN_AVG_VOLUME:
        return []

    events = []
    n = len(df)
    i = 0
    while i < n - 5:
        start_price = closes[i]
        if start_price < MIN_PRICE or start_price <= 0:
            i += 1
            continue
        # window 内の最大 high を見る (intraday touch も含む)
        end = min(i + WINDOW, n - 1)
        window_high = highs[i:end + 1]
        max_idx_local = int(np.argmax(window_high))
        max_val = window_high[max_idx_local]
        if max_val >= start_price * THRESHOLD:
            peak_idx = i + max_idx_local
            events.append({
                "code": code,
                "trough_idx": i,
                "trough_date": str(dates[i]),
                "trough_price": float(start_price),
                "peak_idx": peak_idx,
                "peak_date": str(dates[peak_idx]),
                "peak_price": float(max_val),
                "ratio": float(max_val / start_price),
                "days": int(peak_idx - i),
            })
            # 重複抑制: 次の探索は peak の後ろから
            i = peak_idx + 1
        else:
            i += 1

    # さらに dedupe: 隣接 trough をまとめる
    return events


def stage1_doublers():
    print(f"[Stage1] Connecting {DB}")
    con = sqlite3.connect(DB)
    codes = pd.read_sql("SELECT DISTINCT code FROM daily_prices", con)["code"].tolist()
    print(f"[Stage1] {len(codes)} codes")
    master = load_master()

    all_events: list[dict] = []
    for n, code in enumerate(codes, 1):
        df = pd.read_sql(
            "SELECT date, open, high, low, close, volume FROM daily_prices WHERE code=? ORDER BY date",
            con, params=[code],
        )
        if df.empty:
            continue
        evs = detect_doublers_for_code(df, code)
        for e in evs:
            meta = master.get(str(code), {})
            e.update({
                "name": meta.get("name", ""),
                "sector17": meta.get("sector17", ""),
                "sector33": meta.get("sector33", ""),
                "scale": meta.get("scale", ""),
                "market": meta.get("market", ""),
            })
        all_events.extend(evs)
        if n % 500 == 0:
            print(f"  ... {n}/{len(codes)} codes processed, events so far: {len(all_events)}")

    con.close()
    df = pd.DataFrame(all_events)
    out = CACHE_DIR / "stage1_events.parquet"
    df.to_parquet(out, index=False)
    print(f"[Stage1] saved {len(df)} events -> {out}")
    return df


# ---------- Stage 2: Trend start/end ----------
def stage2_trend():
    src = CACHE_DIR / "stage1_events.parquet"
    if not src.exists():
        print("[Stage2] missing stage1; run --stage 1 first")
        return
    events = pd.read_parquet(src)
    print(f"[Stage2] {len(events)} events to enrich")
    con = sqlite3.connect(DB)

    out_rows = []
    for code, grp in events.groupby("code"):
        df = pd.read_sql(
            "SELECT date, open, high, low, close, volume FROM daily_prices WHERE code=? ORDER BY date",
            con, params=[code],
        )
        if df.empty:
            continue
        df = df.reset_index(drop=True)
        closes = df["close"].values.astype(float)
        highs = df["high"].values.astype(float)
        vols = df["volume"].values.astype(float)
        dates = df["date"].values

        for _, ev in grp.iterrows():
            ti = int(ev["trough_idx"])
            pi = int(ev["peak_idx"])
            # ---- 上昇トレンド開始日: trough の前60営業日で local min を遡って探索
            look_back = max(0, ti - 60)
            lb_seg = closes[look_back:ti + 1]
            tstart_local = int(np.argmin(lb_seg))
            trend_start_idx = look_back + tstart_local
            trend_start_date = str(dates[trend_start_idx])
            trend_start_price = float(closes[trend_start_idx])

            # ---- 下落トレンド開始日: peak から 20% 下落した最初の日 (60営業日先まで)
            look_fwd = min(len(df) - 1, pi + 60)
            running_max = closes[pi]
            running_max_idx = pi
            decline_start_idx = None
            for j in range(pi, look_fwd + 1):
                if closes[j] > running_max:
                    running_max = closes[j]
                    running_max_idx = j
                if closes[j] <= running_max * 0.80:
                    decline_start_idx = running_max_idx  # 下落開始 = 最後のピーク
                    break
            if decline_start_idx is None:
                decline_start_idx = running_max_idx
            decline_start_date = str(dates[decline_start_idx])
            decline_start_price = float(closes[decline_start_idx])

            # ---- 区間特性: 上昇期間の出来高, 価格動向
            seg = df.iloc[trend_start_idx:decline_start_idx + 1]
            if len(seg) < 5:
                continue
            seg_closes = seg["close"].values.astype(float)
            seg_vols = seg["volume"].values.astype(float)
            seg_highs = seg["high"].values.astype(float)
            seg_lows = seg["low"].values.astype(float)

            # ボラ・形状指標
            daily_ret = np.diff(np.log(seg_closes))
            vol_pct = float(np.std(daily_ret) * np.sqrt(252)) if len(daily_ret) > 1 else 0.0
            max_dd_in_run = 0.0
            running = seg_closes[0]
            for c in seg_closes:
                running = max(running, c)
                dd = (c / running) - 1.0
                if dd < max_dd_in_run:
                    max_dd_in_run = dd

            # ギャップアップ回数
            opens = seg["open"].values.astype(float)
            prev_close = np.concatenate([[opens[0]], seg_closes[:-1]])
            gaps = (opens / prev_close) - 1.0
            gap_up_count = int(np.sum(gaps > 0.05))

            # 出来高スパイク (中央比 2.5x 超の日数)
            vol_med = float(np.median(seg_vols)) if len(seg_vols) else 0
            vol_spikes = int(np.sum(seg_vols > vol_med * 2.5)) if vol_med > 0 else 0
            vol_avg = float(np.mean(seg_vols))
            vol_max = float(np.max(seg_vols))

            # トレンド開始直後の急騰判定 (初日〜10日で +30%)
            early_seg = seg_closes[:min(10, len(seg_closes))]
            early_pct = float((early_seg.max() / early_seg[0]) - 1.0) if len(early_seg) > 0 else 0.0

            # ブレイクアウト判定: trough_price がそれ以前52週高値の +/-5% 圏か
            pre_lookup_start = max(0, trend_start_idx - 252)
            pre_seg_high = float(highs[pre_lookup_start:trend_start_idx].max()) if trend_start_idx > pre_lookup_start else 0
            base_prox = float(closes[trend_start_idx] / pre_seg_high) if pre_seg_high > 0 else 0

            # トータル上昇率 (start -> peak)
            total_up = float(closes[pi] / trend_start_price - 1.0)
            run_days = int(decline_start_idx - trend_start_idx)

            out_rows.append({
                **ev.to_dict(),
                "trend_start_date": trend_start_date,
                "trend_start_price": trend_start_price,
                "decline_start_date": decline_start_date,
                "decline_start_price": decline_start_price,
                "run_days": run_days,
                "total_up_pct": total_up * 100,
                "max_dd_in_run_pct": max_dd_in_run * 100,
                "ann_vol_pct": vol_pct * 100,
                "gap_up_count": gap_up_count,
                "vol_spikes": vol_spikes,
                "vol_avg": vol_avg,
                "vol_max": vol_max,
                "early_10d_pct": early_pct * 100,
                "base_proximity": base_prox,
            })
    con.close()
    df = pd.DataFrame(out_rows)
    out = CACHE_DIR / "stage2_trend.parquet"
    df.to_parquet(out, index=False)
    print(f"[Stage2] saved {len(df)} -> {out}")
    return df


# ---------- Stage 3: Pattern classification ----------
def classify_pattern(row) -> str:
    """ヒューリスティック分類 (優先順位付き):
    - Parabolic     : ann_vol >= 100 AND total_up >= 150 AND run_days <= 50 (爆騰)
    - Gap-up連発    : gap_up_count >= 5 (頻繁な窓開け)
    - Acceleration  : run_days <= 20 AND total_up >= 80 (短期急騰)
    - Breakout      : base_proximity >= 0.90 AND early_10d_pct >= 15 (高値ブレイク)
    - V-recovery    : base_proximity < 0.5 AND run_days >= 25 (底値からの回復)
    - Slow-grind    : run_days >= 50 AND ann_vol < 70 (じわ上げ)
    - Mid-pace      : 上記いずれにも当てはまらない中庸ケース
    """
    rd = row["run_days"]; up = row["total_up_pct"]; vol = row["ann_vol_pct"]
    bp = row["base_proximity"]; e10 = row["early_10d_pct"]; gu = row["gap_up_count"]
    if vol >= 100 and up >= 150 and rd <= 50:
        return "Parabolic"
    if gu >= 5:
        return "Gap-up連発"
    if rd <= 20 and up >= 80:
        return "Acceleration"
    if bp >= 0.90 and e10 >= 15:
        return "Breakout"
    if bp < 0.5 and rd >= 25:
        return "V-recovery"
    if rd >= 50 and vol < 70:
        return "Slow-grind"
    return "Mid-pace"


def stage3_classify():
    src = CACHE_DIR / "stage2_trend.parquet"
    if not src.exists():
        print("[Stage3] missing stage2"); return
    df = pd.read_parquet(src)
    df["pattern"] = df.apply(classify_pattern, axis=1)
    out = CACHE_DIR / "stage3_classified.parquet"
    df.to_parquet(out, index=False)
    print(f"[Stage3] {len(df)} classified -> {out}")
    print(df["pattern"].value_counts())
    return df


# ---------- Stage 4: Index + financial + volume context ----------
def get_index_data():
    cache = CACHE_DIR / "indices.parquet"
    if cache.exists():
        return pd.read_parquet(cache)
    import yfinance as yf
    print("[Stage4] fetching indices via yfinance...")
    tickers = {"nikkei": "^N225", "sp500": "^GSPC", "dow": "^DJI", "topix": "1306.T"}
    frames = {}
    for k, t in tickers.items():
        d = yf.download(t, start="2020-01-01", end="2026-05-01", progress=False, auto_adjust=True)
        if d.empty:
            print(f"  WARN empty {k}"); continue
        # yfinance may return MultiIndex columns; flatten
        if isinstance(d.columns, pd.MultiIndex):
            d.columns = [c[0] for c in d.columns]
        d = d.reset_index()[["Date", "Close"]].rename(columns={"Date": "date", "Close": k})
        d["date"] = pd.to_datetime(d["date"]).dt.strftime("%Y-%m-%d")
        frames[k] = d
    out = None
    for k, d in frames.items():
        out = d if out is None else out.merge(d, on="date", how="outer")
    out = out.sort_values("date").reset_index(drop=True)
    out.to_parquet(cache, index=False)
    print(f"[Stage4] indices cached -> {cache}")
    return out


def get_fins_for_code(code: str, near_date: str) -> dict:
    """イベント開始時点直前の通期OPなどを取得"""
    if not FINS_DB.exists():
        return {}
    con = sqlite3.connect(FINS_DB)
    # fins_data.db はスキーマで code 列を確認済み
    try:
        df = pd.read_sql(
            "SELECT * FROM fins WHERE code=? AND date<=? ORDER BY date DESC LIMIT 8",
            con, params=[code, near_date]
        )
    except Exception:
        df = pd.DataFrame()
    con.close()
    if df.empty:
        return {}
    last = df.iloc[0]
    return {
        "fin_date": str(last.get("date", "")),
        "fin_period": str(last.get("period", "")),
        "fin_op": float(last.get("op") or 0),
        "fin_np": float(last.get("np") or 0),
        "fin_eps": float(last.get("eps") or 0),
        "fin_sales": float(last.get("sales") or 0),
        "fin_equity_ratio": float(last.get("equity_ratio") or 0),
        "fin_forecast_eps": float(last.get("forecast_eps") or 0),
    }


def stage4_context():
    src = CACHE_DIR / "stage3_classified.parquet"
    if not src.exists():
        print("[Stage4] missing stage3"); return
    df = pd.read_parquet(src)
    indices = get_index_data()

    # トレンド期間の指数騰落率を付与
    idx_dict = indices.set_index("date").to_dict("index")
    cols = [c for c in indices.columns if c != "date"]

    def _ret(start, end, col):
        if start not in idx_dict or end not in idx_dict:
            # 近接日へ
            sd = indices[indices["date"] <= start].tail(1)
            ed = indices[indices["date"] >= end].head(1)
            if sd.empty or ed.empty: return None
            sv = sd.iloc[0][col]; ev = ed.iloc[0][col]
        else:
            sv = idx_dict[start].get(col); ev = idx_dict[end].get(col)
        if sv is None or ev is None or pd.isna(sv) or pd.isna(ev) or sv == 0:
            return None
        return (ev / sv - 1.0) * 100

    enriched = []
    fin_cache = {}
    for _, row in df.iterrows():
        ts = row["trend_start_date"]; te = row["decline_start_date"]
        rec = row.to_dict()
        for c in cols:
            rec[f"idx_{c}_pct"] = _ret(ts, te, c)
        # 財務 (キャッシュ)
        key = (row["code"], row["trend_start_date"][:7])
        if key not in fin_cache:
            fin_cache[key] = get_fins_for_code(str(row["code"]), row["trend_start_date"])
        rec.update(fin_cache[key])
        enriched.append(rec)

    out = pd.DataFrame(enriched)
    p = CACHE_DIR / "stage4_full.parquet"
    out.to_parquet(p, index=False)
    print(f"[Stage4] saved {len(out)} -> {p}")
    return out


# ---------- Stage 5: Excel output ----------
def stage5_excel():
    src = CACHE_DIR / "stage4_full.parquet"
    if not src.exists():
        print("[Stage5] missing stage4"); return
    df = pd.read_parquet(src)
    print(f"[Stage5] {len(df)} rows")

    # Year buckets
    df["trend_start_year"] = df["trend_start_date"].str[:4]
    df["trend_start_ym"] = df["trend_start_date"].str[:7]

    today = datetime.now().strftime("%Y%m%d")
    out = OUT_DIR / f"doubler_analysis_{today}.xlsx"

    with pd.ExcelWriter(out, engine="openpyxl") as xw:
        # Sheet1: Summary
        sm = pd.DataFrame({
            "指標": [
                "総イベント数",
                "ユニーク銘柄数",
                "対象期間 (上昇開始日)",
                "平均上昇率 (%)",
                "中央上昇率 (%)",
                "平均上昇期間 (営業日)",
                "中央上昇期間 (営業日)",
                "最大上昇率 (%)",
                "最速2倍達成 (営業日)",
            ],
            "値": [
                len(df),
                df["code"].nunique(),
                f"{df['trend_start_date'].min()} 〜 {df['trend_start_date'].max()}",
                round(df["total_up_pct"].mean(), 2),
                round(df["total_up_pct"].median(), 2),
                round(df["run_days"].mean(), 1),
                int(df["run_days"].median()),
                round(df["total_up_pct"].max(), 2),
                int(df["days"].min()),
            ],
        })
        sm.to_excel(xw, sheet_name="サマリー", index=False)

        # Sheet2: All events
        cols_order = [
            "code", "name", "sector17", "sector33", "scale", "market", "pattern",
            "trend_start_date", "trend_start_price",
            "trough_date", "trough_price",
            "peak_date", "peak_price", "ratio",
            "decline_start_date", "decline_start_price",
            "days", "run_days", "total_up_pct", "max_dd_in_run_pct",
            "ann_vol_pct", "gap_up_count", "vol_spikes", "vol_avg", "vol_max",
            "early_10d_pct", "base_proximity",
            "idx_nikkei_pct", "idx_sp500_pct", "idx_dow_pct", "idx_topix_pct",
            "fin_date", "fin_period", "fin_op", "fin_np", "fin_eps", "fin_sales",
            "fin_equity_ratio", "fin_forecast_eps",
        ]
        cols_order = [c for c in cols_order if c in df.columns]
        df_full = df[cols_order].sort_values(["trend_start_date", "ratio"], ascending=[False, False])
        df_full.to_excel(xw, sheet_name="全イベント", index=False)

        # Sheet3: Pattern stats
        pat_stats = df.groupby("pattern").agg(
            イベント数=("code", "size"),
            平均上昇率=("total_up_pct", "mean"),
            中央上昇率=("total_up_pct", "median"),
            平均期間日数=("run_days", "mean"),
            平均DD=("max_dd_in_run_pct", "mean"),
            平均ボラ=("ann_vol_pct", "mean"),
            ギャップ平均=("gap_up_count", "mean"),
            出来高Spike平均=("vol_spikes", "mean"),
            日経連動=("idx_nikkei_pct", "mean"),
        ).round(2).reset_index().sort_values("イベント数", ascending=False)
        pat_stats.to_excel(xw, sheet_name="パターン別統計", index=False)

        # Sheet4: Yearly aggregation (時期分析)
        yr = df.groupby("trend_start_year").agg(
            イベント数=("code", "size"),
            平均上昇率=("total_up_pct", "mean"),
            日経連動=("idx_nikkei_pct", "mean"),
            SP500連動=("idx_sp500_pct", "mean"),
            ダウ連動=("idx_dow_pct", "mean"),
            TOPIX連動=("idx_topix_pct", "mean"),
        ).round(2).reset_index()
        yr.to_excel(xw, sheet_name="年別分析", index=False)

        # Sheet5: Monthly distribution
        ym = df.groupby("trend_start_ym").size().reset_index(name="イベント数")
        ym.to_excel(xw, sheet_name="月別分布", index=False)

        # Sheet6: Sector ranking
        sec = df.groupby(["sector17", "sector33"]).agg(
            イベント数=("code", "size"),
            平均上昇率=("total_up_pct", "mean"),
            ユニーク銘柄数=("code", pd.Series.nunique),
        ).round(2).reset_index().sort_values("イベント数", ascending=False)
        sec.to_excel(xw, sheet_name="セクター別", index=False)

        # Sheet7: Top performers
        top = df.sort_values("total_up_pct", ascending=False).head(100)
        top[cols_order].to_excel(xw, sheet_name="TOP100上昇率", index=False)

        # Sheet8: 出来高分析
        vol_stats = df.groupby("pattern").agg(
            平均出来高=("vol_avg", "mean"),
            最大出来高=("vol_max", "mean"),
            出来高Spike平均=("vol_spikes", "mean"),
            ギャップアップ平均=("gap_up_count", "mean"),
        ).round(0).reset_index()
        vol_stats.to_excel(xw, sheet_name="出来高分析", index=False)

        # Sheet9: 財務スナップショット (上位)
        fin_view = df.dropna(subset=["fin_op"])[
            ["code", "name", "sector17", "trend_start_date", "total_up_pct", "pattern",
             "fin_date", "fin_period", "fin_op", "fin_np", "fin_eps", "fin_sales", "fin_equity_ratio"]
        ].sort_values("total_up_pct", ascending=False).head(200)
        fin_view.to_excel(xw, sheet_name="財務スナップ", index=False)

    print(f"[Stage5] saved -> {out}")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", default="all", help="1|2|3|4|5|all")
    args = ap.parse_args()
    s = args.stage
    if s in ("1", "all"): stage1_doublers()
    if s in ("2", "all"): stage2_trend()
    if s in ("3", "all"): stage3_classify()
    if s in ("4", "all"): stage4_context()
    if s in ("5", "all"): stage5_excel()


if __name__ == "__main__":
    main()
