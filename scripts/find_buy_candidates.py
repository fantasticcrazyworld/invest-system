"""
購入候補抽出: Doubler特徴量+ミネルヴィニ+RSの統合スコア。

候補ティア:
  ★★★ S候補: ミネルヴィニ score>=6 + doubler_score>=6 + RS26w>=0
  ★★  A候補: score>=5 + doubler_score>=5
  ★   B候補: score>=4 + doubler_score>=4 OR (リピーター+score>=5)
  監視  W候補: doubler_score>=7 (純シグナル)

各候補に推奨損切り・目標を計算して出力。
"""
from __future__ import annotations
import json
from pathlib import Path
import pandas as pd

REPO = Path(r"C:/Users/yohei/Documents/invest-system-github")
SRC = REPO / "data" / "screen_full_with_doubler.json"
OUT_MD = REPO / "reports" / "analysis" / "buy_candidates_20260415.md"
OUT_JSON = REPO / "reports" / "analysis" / "buy_candidates_20260415.json"


def _to_num(v, default=0):
    if v is None or v == "":
        return default
    if isinstance(v, str) and "/" in v:
        try:
            return float(v.split("/")[0])
        except ValueError:
            return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def classify(item: dict) -> str | None:
    sc = _to_num(item.get("score"))
    d = item.get("doubler", {}) or {}
    ds = _to_num(d.get("doubler_score"))
    rs26 = _to_num(item.get("rs26w"))
    rs50 = _to_num(item.get("rs50w"))
    rep = bool(d.get("is_repeater"))
    tier = d.get("repeat_tier")

    if sc >= 6 and ds >= 6 and rs26 >= 0:
        return "S"
    if sc >= 5 and ds >= 5:
        return "A"
    if (sc >= 4 and ds >= 4) or (rep and sc >= 5 and tier in ("S", "A")):
        return "B"
    if ds >= 7:
        return "W"
    return None


def build_row(item: dict, tier: str) -> dict:
    d = item.get("doubler", {}) or {}
    price = item.get("price")
    sma50 = item.get("sma50")
    sl_pct = d.get("sl_distance_recommended_pct", 10)
    sl_price = round(price * (1 - sl_pct / 100), 1) if price else None
    # 目標: パターン別 平均上昇率の半分(保守) と 全期間中央値 +127% で2案
    target_conservative = round(price * 1.30, 1) if price else None  # +30%
    target_main = round(price * 1.60, 1) if price else None          # +60%
    return {
        "tier": tier,
        "code": item.get("code"),
        "name": item.get("name"),
        "price": price,
        "score": item.get("score"),
        "doubler_score": d.get("doubler_score"),
        "estimated_pattern": d.get("estimated_pattern"),
        "is_repeater": d.get("is_repeater"),
        "repeat_tier": d.get("repeat_tier"),
        "repeat_count": d.get("repeat_count"),
        "max_past_up_pct": d.get("max_past_up_pct"),
        "rs6w": item.get("rs6w"),
        "rs13w": item.get("rs13w"),
        "rs26w": item.get("rs26w"),
        "rs50w": item.get("rs50w"),
        "vol_ratio": item.get("vol_ratio"),
        "change_pct": item.get("change_pct"),
        "gap_up_count_13w": d.get("gap_up_count_13w"),
        "vol_spike_count_13w": d.get("vol_spike_count_13w"),
        "vol_surge_ratio": d.get("vol_surge_ratio"),
        "early_run_pct_10d": d.get("early_run_pct_10d"),
        "sl_distance_pct": sl_pct,
        "sl_price": sl_price,
        "target_conservative": target_conservative,
        "target_main": target_main,
        "sma50": sma50,
    }


def main():
    raw = json.loads(SRC.read_text(encoding="utf-8"))
    rows = []
    for code, item in raw.items():
        if not isinstance(item, dict) or not item.get("price"):
            continue
        # 流動性: 直近出来高比 0.3x未満は除外
        vr = item.get("vol_ratio")
        if vr is not None and vr < 0.3:
            continue
        # 株価フィルタ: 50円未満は除外（ボロ株）
        if item.get("price", 0) < 50:
            continue
        t = classify(item)
        if t:
            rows.append(build_row(item, t))

    df = pd.DataFrame(rows)
    if df.empty:
        print("候補なし")
        return

    # 整列: tier(S<A<B<W) 内で doubler_score+score 降順
    tier_order = {"S": 0, "A": 1, "B": 2, "W": 3}
    df["tier_rank"] = df["tier"].map(tier_order)
    df["doubler_score"] = pd.to_numeric(df["doubler_score"], errors="coerce").fillna(0)
    df["score_num"] = df["score"].apply(_to_num)
    df["combined"] = df["doubler_score"] + df["score_num"]
    df = df.sort_values(["tier_rank", "combined"], ascending=[True, False]).drop(columns=["tier_rank","combined"])

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(df.to_json(orient="records", force_ascii=False, indent=2), encoding="utf-8")

    # Markdown
    today = "2026-04-15"
    md = [f"# 購入候補リスト {today}", ""]
    md.append(f"基準: ミネルヴィニscore + Doubler特徴量(ギャップ・出来高Spike・リピーター)の統合判定")
    md.append("")
    md.append(f"**総候補数: {len(df)}** (S:{(df['tier']=='S').sum()} / A:{(df['tier']=='A').sum()} / B:{(df['tier']=='B').sum()} / W:{(df['tier']=='W').sum()})")
    md.append("")

    for tier, label in [("S","★★★ S候補（最優先・即時検討）"), ("A","★★ A候補（条件良好）"), ("B","★ B候補（観察中）"), ("W","◎ W候補（Doubler特化監視）")]:
        sub = df[df["tier"] == tier].head(20)
        if sub.empty:
            continue
        md.append(f"## {label} ({len(df[df['tier']==tier])}件)")
        md.append("")
        md.append("| code | 銘柄 | 株価 | M-score | D-score | パターン推定 | リピート | RS26w | ギャップ13w | Vol-Surge | 推奨SL価格(-%) | 主目標(+60%) |")
        md.append("|------|------|-----:|--------:|--------:|------------|---------|------:|------:|------:|--------:|--------:|")
        for _, r in sub.iterrows():
            rep_mark = f"{r['repeat_tier']}({r['repeat_count']}回)" if r["is_repeater"] else "—"
            md.append(
                f"| {r['code']} | {r['name'][:18]} | {r['price']:.1f} | "
                f"{int(_to_num(r['score']))}/7 | {int(r['doubler_score'] or 0)}/10 | "
                f"{r['estimated_pattern']} | {rep_mark} | "
                f"{(r['rs26w'] or 0):+.2f} | {int(r['gap_up_count_13w'] or 0)} | "
                f"{(r['vol_surge_ratio'] or 0):.2f}x | "
                f"{r['sl_price']}(-{r['sl_distance_pct']:.0f}%) | {r['target_main']} |"
            )
        md.append("")

    OUT_MD.write_text("\n".join(md), encoding="utf-8")
    print(f"Saved -> {OUT_MD}")
    print(f"Saved -> {OUT_JSON}")
    print()
    print(f"Total candidates: {len(df)}")
    print(df.groupby("tier").size())


if __name__ == "__main__":
    main()
