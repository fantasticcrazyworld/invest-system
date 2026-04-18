"""パターン検出: カップウィズハンドル・VCP・フラットベース等の MCP tool 群。

ミネルヴィニ / オニール流ブレイクアウトパターンの自動検出。
detect_patterns / screen_patterns の 2 つの MCP tool を提供。
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from mcp_server._context import mcp, RESULTS_FILE


# _load_daily_csv は stock_mcp_server.py 側に残存中。遅延 import で循環回避。
def _load_daily_csv(code: str) -> pd.DataFrame:
    from stock_mcp_server import _load_daily_csv as _impl
    return _impl(code)


def _find_swing_highs(closes: list, window: int = 10) -> list:
    """Find swing high indices (local maxima)."""
    highs = []
    for i in range(window, len(closes) - window):
        if closes[i] == max(closes[i - window: i + window + 1]):
            highs.append(i)
    return highs


def _find_swing_lows(closes: list, window: int = 10) -> list:
    """Find swing low indices (local minima)."""
    lows = []
    for i in range(window, len(closes) - window):
        if closes[i] == min(closes[i - window: i + window + 1]):
            lows.append(i)
    return lows


def _detect_cup_with_handle(df: pd.DataFrame) -> dict:
    """
    Cup with Handle detection.
    - Cup: U-shaped base, 15-65 days, depth 12-35%
    - Handle: shallow pullback from right rim, 5-25 days, < 1/2 cup depth
    - Pivot: handle high + small buffer
    """
    closes = df["close"].values.astype(float).tolist()
    n = len(closes)
    if n < 60:
        return {"detected": False, "confidence": 0, "details": {}}

    # Search for cup patterns in recent data (last 120 days)
    search_start = max(0, n - 120)
    best = None

    swing_highs = _find_swing_highs(closes[search_start:], window=8)
    swing_highs = [i + search_start for i in swing_highs]

    for left_rim_idx in swing_highs:
        left_rim_price = closes[left_rim_idx]

        # Look for cup bottom after left rim
        cup_end_range = min(left_rim_idx + 66, n)
        if cup_end_range - left_rim_idx < 15:
            continue

        segment = closes[left_rim_idx:cup_end_range]
        bottom_offset = segment.index(min(segment))
        bottom_idx = left_rim_idx + bottom_offset
        bottom_price = closes[bottom_idx]

        cup_depth_pct = (left_rim_price - bottom_price) / left_rim_price
        if not (0.12 <= cup_depth_pct <= 0.35):
            continue

        # Check U-shape: bottom should be roughly in middle third
        cup_len = cup_end_range - left_rim_idx
        if not (cup_len * 0.25 < bottom_offset < cup_len * 0.75):
            continue

        # Right rim: find recovery back toward left rim price
        right_rim_idx = None
        for j in range(bottom_idx + 5, min(bottom_idx + 50, n)):
            if closes[j] >= left_rim_price * 0.95:
                right_rim_idx = j
                break
        if right_rim_idx is None:
            continue

        # Handle: shallow pullback after right rim
        handle_end = min(right_rim_idx + 26, n)
        if handle_end - right_rim_idx < 5:
            continue

        handle_seg = closes[right_rim_idx:handle_end]
        handle_low = min(handle_seg)
        handle_depth_pct = (closes[right_rim_idx] - handle_low) / closes[right_rim_idx]

        # Handle should be shallow (less than half of cup depth)
        if handle_depth_pct > cup_depth_pct * 0.5:
            continue
        if handle_depth_pct < 0.02:
            continue

        # Pivot price: right rim high + 0.5%
        pivot_price = max(handle_seg) * 1.005

        confidence = min(1.0, 0.5
                         + (0.2 if 0.15 <= cup_depth_pct <= 0.30 else 0)
                         + (0.15 if handle_depth_pct <= cup_depth_pct * 0.33 else 0)
                         + (0.15 if cup_len >= 25 else 0))

        if best is None or confidence > best["confidence"]:
            reason = (
                f"左リム{left_rim_price:.0f}円→底{bottom_price:.0f}円"
                f"(深さ{cup_depth_pct*100:.1f}%)→右リム回復。"
                f"ハンドル調整{handle_depth_pct*100:.1f}%。"
                f"ピボット{pivot_price:.0f}円。"
                f"カップ期間{right_rim_idx - left_rim_idx}日"
            )
            best = {
                "detected": True,
                "confidence": round(confidence, 2),
                "reason": reason,
                "details": {
                    "left_rim_idx": left_rim_idx,
                    "left_rim_price": round(left_rim_price, 1),
                    "bottom_idx": bottom_idx,
                    "bottom_price": round(bottom_price, 1),
                    "right_rim_idx": right_rim_idx,
                    "cup_depth_pct": round(cup_depth_pct * 100, 1),
                    "handle_depth_pct": round(handle_depth_pct * 100, 1),
                    "cup_length_days": right_rim_idx - left_rim_idx,
                    "pivot_price": round(pivot_price, 1),
                },
            }

    return best or {"detected": False, "confidence": 0, "details": {}}


def _detect_vcp(df: pd.DataFrame) -> dict:
    """
    VCP (Volatility Contraction Pattern) detection.
    - At least 2 contractions where range shrinks 20%+ each time
    - Volume declining during contractions
    """
    closes = df["close"].values.astype(float)
    highs = df["high"].values.astype(float)
    lows = df["low"].values.astype(float)
    volumes = df["volume"].values.astype(float)
    n = len(closes)
    if n < 40:
        return {"detected": False, "confidence": 0, "details": {}}

    # Analyze last 80 days
    lookback = min(80, n)
    start = n - lookback

    # Find contractions: split into segments by swing highs
    seg_ranges = []
    seg_volumes = []
    seg_size = lookback // 4  # ~20 day segments

    for i in range(4):
        s = start + i * seg_size
        e = min(s + seg_size, n)
        if e <= s:
            break
        seg_high = max(highs[s:e])
        seg_low = min(lows[s:e])
        seg_range_pct = (seg_high - seg_low) / seg_high if seg_high > 0 else 0
        seg_ranges.append(seg_range_pct)
        seg_volumes.append(sum(volumes[s:e]) / (e - s))

    if len(seg_ranges) < 3:
        return {"detected": False, "confidence": 0, "details": {}}

    # Count contractions (range shrinking)
    contractions = 0
    vol_declining = 0
    for i in range(1, len(seg_ranges)):
        if seg_ranges[i] < seg_ranges[i - 1] * 0.85:
            contractions += 1
        if seg_volumes[i] < seg_volumes[i - 1]:
            vol_declining += 1

    detected = contractions >= 2
    if not detected:
        return {"detected": False, "confidence": 0, "details": {}}

    # Resistance line: recent swing high
    recent_high = max(highs[n - 20:])
    confidence = min(1.0, 0.4
                     + contractions * 0.15
                     + vol_declining * 0.1)

    ranges_str = "→".join(f"{r*100:.1f}%" for r in seg_ranges)
    reason = (
        f"収縮{contractions}回検出。レンジ: {ranges_str}。"
        f"出来高減少{vol_declining}回。"
        f"レジスタンス{recent_high:.0f}円"
    )
    return {
        "detected": True,
        "confidence": round(confidence, 2),
        "reason": reason,
        "details": {
            "contractions": contractions,
            "vol_declining_segments": vol_declining,
            "ranges_pct": [round(r * 100, 1) for r in seg_ranges],
            "resistance": round(float(recent_high), 1),
            "current_range_pct": round(seg_ranges[-1] * 100, 1),
        },
    }


def _detect_flat_base(df: pd.DataFrame) -> dict:
    """
    Flat Base detection.
    - Range within 15% over 20-65 days
    - Volume below average
    """
    closes = df["close"].values.astype(float)
    volumes = df["volume"].values.astype(float)
    n = len(closes)
    if n < 20:
        return {"detected": False, "confidence": 0, "details": {}}

    avg_vol = volumes[-min(100, n):].mean()
    best = None

    for length in range(20, min(66, n)):
        seg = closes[-length:]
        seg_high = max(seg)
        seg_low = min(seg)
        range_pct = (seg_high - seg_low) / seg_high if seg_high > 0 else 0

        if range_pct > 0.15:
            continue

        seg_vol = volumes[-length:]
        vol_ratio = seg_vol.mean() / avg_vol if avg_vol > 0 else 1.0

        confidence = min(1.0, 0.5
                         + (0.2 if range_pct <= 0.10 else 0)
                         + (0.15 if vol_ratio < 0.8 else 0)
                         + (0.15 if length >= 30 else 0))

        if best is None or confidence > best["confidence"]:
            reason = (
                f"直近{length}日間のレンジ{range_pct*100:.1f}%"
                f"(高値{seg_high:.0f}円-安値{seg_low:.0f}円)。"
                f"出来高比{vol_ratio:.2f}倍。"
                f"レジスタンス{seg_high:.0f}円"
            )
            best = {
                "detected": True,
                "confidence": round(confidence, 2),
                "reason": reason,
                "details": {
                    "length_days": length,
                    "range_pct": round(range_pct * 100, 1),
                    "high": round(float(seg_high), 1),
                    "low": round(float(seg_low), 1),
                    "vol_ratio": round(vol_ratio, 2),
                    "resistance": round(float(seg_high), 1),
                },
            }

    return best or {"detected": False, "confidence": 0, "details": {}}


def _detect_all_patterns(df: pd.DataFrame) -> dict:
    """Run all pattern detectors on a DataFrame."""
    return {
        "cup_with_handle": _detect_cup_with_handle(df),
        "vcp": _detect_vcp(df),
        "flat_base": _detect_flat_base(df),
    }


@mcp.tool()
def detect_patterns(code: str) -> str:
    """銘柄のチャートパターンを検出する。

    Cup with Handle / VCP / Flat Base を判定。
    既存CSVデータを使用（APIコストなし）。CSVがなければAPIから取得。

    Args:
        code: 4桁銘柄コード
    """
    df = _load_daily_csv(code)
    if df.empty:
        try:
            bars = _fetch_daily(code)
            if not bars:
                return json.dumps({"error": f"No data for {code}"}, ensure_ascii=False)
            df = _daily_to_df(bars)
            df.reset_index().to_csv(CSV_DIR / f"{code}_daily.csv", index=False)
        except Exception as e:
            return json.dumps({"error": str(e)}, ensure_ascii=False)

    results = _detect_all_patterns(df)
    results["code"] = code
    results["data_days"] = len(df)

    # Summary line
    detected = [k for k, v in results.items()
                if isinstance(v, dict) and v.get("detected")]
    results["summary"] = (
        f"{code}: {', '.join(detected)} detected" if detected
        else f"{code}: No pattern detected"
    )

    return json.dumps(results, ensure_ascii=False, indent=2)


@mcp.tool()
def screen_patterns(min_score: int = 6) -> str:
    """スクリーニングPASS銘柄のチャートパターンを一括検出する。

    screen_full の結果からスコアが min_score 以上の銘柄を対象に
    Cup with Handle / VCP / Flat Base を検出。APIコストなし（CSV使用）。

    Args:
        min_score: 最低スコア（デフォルト6）
    """
    if not RESULTS_FILE.exists():
        return "ERROR: screen_full results not found. Run screen_full first."

    data = json.loads(RESULTS_FILE.read_text(encoding="utf-8"))
    # Build lookup: code -> item
    items = data.values() if isinstance(data, dict) else data
    lookup = {}
    for item in items:
        if isinstance(item, dict) and item.get("code"):
            lookup[item["code"]] = item

    candidates = []
    for code, item in lookup.items():
        score_str = item.get("score", "0/7")
        score = int(score_str.split("/")[0])
        if score >= min_score:
            candidates.append(code)

    if not candidates:
        return f"No stocks with score >= {min_score}"

    all_results = []
    for code in candidates:
        df = _load_daily_csv(code)
        if df.empty:
            all_results.append({"code": code, "error": "No CSV data"})
            continue
        patterns = _detect_all_patterns(df)
        detected = [k for k, v in patterns.items() if v.get("detected")]
        item = lookup.get(code, {})
        all_results.append({
            "code": code,
            "name": item.get("name", ""),
            "score": item.get("score", ""),
            "patterns": detected,
            "details": {k: v for k, v in patterns.items() if v.get("detected")},
        })

    # Separate: with patterns vs without
    with_patterns = [r for r in all_results if r.get("patterns")]
    without = [r for r in all_results if not r.get("patterns") and "error" not in r]

    # Save results
    output = {
        "__meta__": {
            "generated_at": datetime.now().isoformat(),
            "total_screened": len(candidates),
            "patterns_found": len(with_patterns),
            "min_score": min_score,
        },
        "with_patterns": with_patterns,
        "no_patterns": [{"code": r["code"], "name": r.get("name", "")}
                        for r in without],
    }

    result_path = BASE_DIR / "data" / "pattern_results.json"
    result_path.write_text(
        json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # Summary
    lines = [f"Pattern screening: {len(candidates)} stocks (score >= {min_score})"]
    lines.append(f"Patterns found: {len(with_patterns)} stocks\n")
    for r in with_patterns:
        patterns_str = ", ".join(r["patterns"])
        lines.append(f"  {r['code']}  {r.get('name',''):<10}  "
                      f"[{r.get('score','')}]  {patterns_str}")

    lines.append(f"\nResults saved to {result_path}")
    return "\n".join(lines)


