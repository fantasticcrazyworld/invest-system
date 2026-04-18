"""
Doubler分析の知見をスクリーニングに統合するための特徴量計算モジュール。

新指標:
  - gap_up_count_6w / 13w  : 5%以上のギャップアップ回数
  - vol_spike_count_6w / 13w : 出来高が中央値2.5倍超の日数
  - max_gap_pct_13w        : 期間内最大ギャップ%
  - vol_surge_ratio        : 直近5日 / 過去60日 出来高比
  - early_run_pct_10d      : 直近10日の最大上昇率
  - is_repeater            : 過去2倍化リスト掲載か (S/A/B/C tier)
  - repeat_tier            : "S" (4回+) / "A" (3回) / "B" (2回) / "C" (1回) / null
  - doubler_score          : 0-10の総合スコア (買い候補絞り込み用)
  - sl_distance_recommended : パターン推奨損切り距離(%)
  - target_run_days        : パターン推奨保有日数

パターン別SL推奨 (Doubler分析より):
  Slow-grind=-7% / Breakout=-8% / Mid-pace=-10% / V-recovery=-10%
  Gap-up連発=-12% / Parabolic=-15% / Acceleration=-8%
"""
from __future__ import annotations
import json, sqlite3
from pathlib import Path
import pandas as pd
import numpy as np

REPO_ROOT = Path(r"C:/Users/yohei/Documents/invest-system-github")
LEGACY_DB = Path(r"C:/Users/yohei/Documents/invest-system/data/stock_prices.db")
PRICE_DB = REPO_ROOT / "data" / "stock_prices.db"
REPEATERS_JSON = REPO_ROOT / "data" / "doubler_repeaters.json"

# パターン別推奨損切り
PATTERN_SL = {
    "Slow-grind": 7.0,
    "Breakout": 8.0,
    "Acceleration": 8.0,
    "Mid-pace": 10.0,
    "V-recovery": 10.0,
    "Gap-up連発": 12.0,
    "Parabolic": 15.0,
}

# パターン別推奨保有日数 (中央値ベース)
PATTERN_DAYS = {
    "Slow-grind": 95,
    "Breakout": 109,
    "Mid-pace": 60,
    "V-recovery": 50,
    "Gap-up連発": 80,
    "Parabolic": 45,
    "Acceleration": 15,
}


def load_repeaters() -> dict[str, dict]:
    if not REPEATERS_JSON.exists():
        return {}
    data = json.loads(REPEATERS_JSON.read_text(encoding="utf-8"))
    out = {}
    for r in data["repeaters"]:
        cnt = r["repeat_count"]
        tier = "S" if cnt >= 4 else "A" if cnt == 3 else "B" if cnt == 2 else "C"
        out[str(r["code"])] = {**r, "tier": tier}
    return out


def calc_features(df: pd.DataFrame) -> dict:
    """1銘柄の価格DataFrameから特徴量を算出.
    df: columns=['date','open','high','low','close','volume'] 日付昇順.
    """
    if len(df) < 30:
        return {}
    df = df.sort_values("date").reset_index(drop=True)
    closes = df["close"].values.astype(float)
    opens = df["open"].values.astype(float)
    highs = df["high"].values.astype(float)
    vols = df["volume"].values.astype(float)

    n = len(df)
    # ギャップアップ (今日の始値 / 前日終値 - 1) >= 5%
    prev_close = np.concatenate([[opens[0]], closes[:-1]])
    gaps = opens / np.where(prev_close > 0, prev_close, np.nan) - 1.0

    # 出来高基準 (過去60日中央値)
    vol_med_60 = float(np.median(vols[-min(60, n):])) if n >= 5 else 0.0

    def _slice(days: int) -> slice:
        return slice(max(0, n - days), n)

    # 6週 (30営業日) / 13週 (65営業日)
    s_6w = _slice(30); s_13w = _slice(65)

    gap_up_6w = int(np.sum(gaps[s_6w] > 0.05))
    gap_up_13w = int(np.sum(gaps[s_13w] > 0.05))
    max_gap_13w = float(np.nanmax(gaps[s_13w]) * 100) if n > 1 else 0.0

    spike_6w = int(np.sum(vols[s_6w] > vol_med_60 * 2.5)) if vol_med_60 > 0 else 0
    spike_13w = int(np.sum(vols[s_13w] > vol_med_60 * 2.5)) if vol_med_60 > 0 else 0

    # 出来高サージ: 直近5日平均 / 過去60日平均
    vol_recent = float(np.mean(vols[-min(5, n):]))
    vol_base = float(np.mean(vols[-min(60, n):]))
    vol_surge = vol_recent / vol_base if vol_base > 0 else 0.0

    # 直近10日 最大上昇率
    last10 = closes[-min(10, n):]
    early_run_10d = float((last10.max() / last10[0] - 1.0) * 100) if len(last10) > 0 else 0.0

    return {
        "gap_up_count_6w": gap_up_6w,
        "gap_up_count_13w": gap_up_13w,
        "max_gap_pct_13w": round(max_gap_13w, 2),
        "vol_spike_count_6w": spike_6w,
        "vol_spike_count_13w": spike_13w,
        "vol_surge_ratio": round(vol_surge, 2),
        "early_run_pct_10d": round(early_run_10d, 2),
    }


def doubler_score(feat: dict, repeater: dict | None) -> int:
    """0-10の総合スコア (高いほど2倍化候補に近い)
    重み:
      gap_up_13w >= 5      : +3
      gap_up_13w >= 3      : +2
      vol_spike_13w >= 5   : +2
      vol_surge_ratio >= 2 : +2
      early_run_10d >= 10  : +1
      repeater Tier S      : +3 (累積最大 +6 → 上限10)
      repeater Tier A      : +2
      repeater Tier B      : +1
    """
    s = 0
    g13 = feat.get("gap_up_count_13w", 0)
    if g13 >= 5: s += 3
    elif g13 >= 3: s += 2
    sp13 = feat.get("vol_spike_count_13w", 0)
    if sp13 >= 5: s += 2
    elif sp13 >= 3: s += 1
    if feat.get("vol_surge_ratio", 0) >= 2: s += 2
    elif feat.get("vol_surge_ratio", 0) >= 1.5: s += 1
    if feat.get("early_run_pct_10d", 0) >= 10: s += 1
    if repeater:
        t = repeater.get("tier", "C")
        if t == "S": s += 3
        elif t == "A": s += 2
        elif t == "B": s += 1
    return min(s, 10)


def estimate_pattern(feat: dict, ann_vol: float | None = None) -> str:
    """直近13週特徴量からパターンを推定（暫定分類）"""
    g13 = feat.get("gap_up_count_13w", 0)
    sp13 = feat.get("vol_spike_count_13w", 0)
    surge = feat.get("vol_surge_ratio", 0)
    e10 = feat.get("early_run_pct_10d", 0)
    if (ann_vol or 0) >= 100 and e10 >= 30:
        return "Parabolic"
    if g13 >= 5:
        return "Gap-up連発"
    if e10 >= 30 and sp13 >= 3:
        return "Acceleration"
    if surge >= 2 and e10 >= 10:
        return "Breakout"
    if e10 < 5 and g13 <= 2:
        return "Slow-grind"
    return "Mid-pace"


def recommend_sl_pct(pattern: str) -> float:
    return PATTERN_SL.get(pattern, 10.0)


def recommend_hold_days(pattern: str) -> int:
    return PATTERN_DAYS.get(pattern, 70)


def augment_screen_results(results_json: Path, output_json: Path | None = None,
                           db_path: Path | None = None) -> Path:
    """既存のscreen_full_results.jsonに新指標を付与"""
    if db_path is None:
        db_path = LEGACY_DB if LEGACY_DB.exists() else PRICE_DB
    raw = json.loads(results_json.read_text(encoding="utf-8"))
    repeaters = load_repeaters()

    con = sqlite3.connect(db_path)
    enriched = {}
    for code, item in raw.items():
        df = pd.read_sql(
            "SELECT date, open, high, low, close, volume FROM daily_prices WHERE code=? ORDER BY date",
            con, params=[str(code)],
        )
        if df.empty:
            enriched[code] = item
            continue
        feat = calc_features(df)
        rep = repeaters.get(str(code))
        score = doubler_score(feat, rep)
        ann_vol = item.get("indicators", {}).get("ann_vol_pct") if isinstance(item, dict) else None
        pattern = estimate_pattern(feat, ann_vol)
        enriched[code] = {
            **item,
            "doubler": {
                **feat,
                "is_repeater": rep is not None,
                "repeat_tier": rep.get("tier") if rep else None,
                "repeat_count": rep.get("repeat_count") if rep else 0,
                "max_past_up_pct": rep.get("max_up_pct") if rep else None,
                "estimated_pattern": pattern,
                "doubler_score": score,
                "sl_distance_recommended_pct": recommend_sl_pct(pattern),
                "hold_days_recommended": recommend_hold_days(pattern),
            },
        }
    con.close()

    out_path = output_json or results_json.with_name("screen_full_with_doubler.json")
    out_path.write_text(json.dumps(enriched, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_path


if __name__ == "__main__":
    src = REPO_ROOT / "data" / "screen_full_results.json"
    out = augment_screen_results(src)
    print(f"Augmented -> {out}")
