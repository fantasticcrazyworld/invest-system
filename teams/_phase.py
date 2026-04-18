"""市場フェーズ判定: Attack / Steady / Defend のルールベース判定。

ミネルヴィニ基準による決定論的アルゴリズム（AI 非依存）。
毎日同じ入力なら同じ出力を返すため、判定の一貫性を保証する。
"""
from __future__ import annotations

from teams._base import _rs26w, _score_num


def detect_phase(screen_data: list) -> dict:
    """
    ミネルヴィニ基準によるルールベースフェーズ判定。
    返り値: {'phase': 'Attack'|'Steady'|'Defend', 'score': int, 'reasons': list}
    """
    score = 0  # +: 強気, -: 弱気
    reasons = []

    if not screen_data:
        return {'phase': 'Defend', 'score': -99, 'reasons': ['スクリーニングデータなし']}

    # ── 1. RS上位銘柄の割合（ブレイクアウト候補の多さ）
    total = len(screen_data)
    high_rs = [s for s in screen_data if isinstance(s, dict) and _rs26w(s) > 1.5]
    rs_ratio = len(high_rs) / total if total > 0 else 0
    if rs_ratio >= 0.15:
        score += 2
        reasons.append(f'[事実] RS26w>1.5の銘柄が{rs_ratio:.0%}（{len(high_rs)}/{total}銘柄） → 強気')
    elif rs_ratio >= 0.08:
        score += 1
        reasons.append(f'[事実] RS26w>1.5の銘柄が{rs_ratio:.0%}（{len(high_rs)}/{total}銘柄） → 中立')
    else:
        score -= 1
        reasons.append(f'[事実] RS26w>1.5の銘柄が{rs_ratio:.0%}（{len(high_rs)}/{total}銘柄） → 弱気')

    # ── 2. スコア7以上（全条件クリア）銘柄の数
    top_stocks = [s for s in screen_data if isinstance(s, dict) and _score_num(s) >= 7]
    if len(top_stocks) >= 10:
        score += 2
        reasons.append(f'[事実] スコア7以上が{len(top_stocks)}銘柄 → 強い候補多数')
    elif len(top_stocks) >= 5:
        score += 1
        reasons.append(f'[事実] スコア7以上が{len(top_stocks)}銘柄 → 候補あり')
    else:
        score -= 1
        reasons.append(f'[事実] スコア7以上が{len(top_stocks)}銘柄 → 候補少なく慎重')

    # ── 3. 平均RSスコアの方向性
    rs_values = [_rs26w(s) for s in screen_data if isinstance(s, dict) and _rs26w(s)]
    avg_rs = sum(rs_values) / len(rs_values) if rs_values else 0
    if avg_rs > 1.2:
        score += 1
        reasons.append(f'[事実] 全銘柄平均RS50w={avg_rs:.2f} → 市場全体が強い')
    elif avg_rs > 0.8:
        reasons.append(f'[事実] 全銘柄平均RS50w={avg_rs:.2f} → 中立水準')
    else:
        score -= 1
        reasons.append(f'[事実] 全銘柄平均RS50w={avg_rs:.2f} → 市場全体が弱い')

    # ── 4. 判定
    if score >= 3:
        phase = 'Attack'
    elif score >= 0:
        phase = 'Steady'
    else:
        phase = 'Defend'

    return {'phase': phase, 'score': score, 'reasons': reasons}


