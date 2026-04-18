"""シミュレーション追跡・検証チーム (Team 8) の内部ヘルパー群。

シナリオ生成・日次乖離分析・セクター多様性チェックなど、
`run_verification()` が依存する純粋関数を集約。
"""
from __future__ import annotations

import json
from pathlib import Path

from teams._base import (
    call_claude, load_json, read_knowledge, write_knowledge,
    _score_num, _rs26w, screen_to_list,
)
from teams._context import TODAY, REPORT_DIR


MAX_SIM_SLOTS = 5  # 同時追跡上限

def _make_new_sim(best: dict) -> dict:
    """候補銘柄からシミュレーションエントリーを生成"""
    ep = best.get('price', 0) or 0
    stop_pct = 0.08
    target_pct = 0.25
    rs26w = _rs26w(best)               # rs26w / rs_26w 両キー対応・float変換
    score_n = _score_num(best)         # "5/7" 形式 → 整数
    return {
        'code': str(best.get('code', '')),
        'name': best.get('name', ''),
        'entry_price': round(ep, 0),
        'stop_loss': round(ep * (1 - stop_pct), 0),
        'target1': round(ep * (1 + target_pct), 0),
        'rr_ratio': round(target_pct / stop_pct, 1),
        'start_date': TODAY,
        'end_date': None,
        'days_elapsed': 0,
        'current_price': ep,
        'current_pct': 0.0,
        'rs_26w': rs26w,
        'score': score_n,
        'result': None,
        'result_pct': None,
        'direction_match': None,
        'reason': f"RS50w={rs26w:.2f}, score={score_n}/7, 上位候補",
        # v2: 3シナリオ・日次ログ・仮説
        'scenarios': None,        # _generate_scenarios() で生成
        'daily_log': [],
        'current_hypothesis': None,
    }


# ─── v2: 3シナリオ ヘルパー関数 ──────────────────────────────────────────────

def _get_week_target(scenarios, scenario_id, days_elapsed):
    """経過日数から対応する週のターゲット%を返す"""
    s = scenarios.get(scenario_id, {})
    if days_elapsed <= 5:    return s.get('w1_pct', 0)
    elif days_elapsed <= 10: return s.get('w2_pct', 0)
    elif days_elapsed <= 15: return s.get('w3_pct', 0)
    else:                    return s.get('w4_pct', 0)


def _determine_leading_scenario(scenarios, cumulative_pct, days_elapsed):
    """現在の累積%に最も近いシナリオを返す"""
    best, best_gap = None, float('inf')
    for sid in ('bull', 'base', 'bear'):
        target = _get_week_target(scenarios, sid, days_elapsed)
        gap = abs(cumulative_pct - target)
        if gap < best_gap:
            best_gap, best = gap, sid
    return best


def _scenario_gaps(scenarios, cumulative_pct, days_elapsed):
    """各シナリオとの乖離（cumulative - target）を返す"""
    return {sid: round(cumulative_pct - _get_week_target(scenarios, sid, days_elapsed), 2)
            for sid in ('bull', 'base', 'bear')}


def _generate_scenarios(sim, context_str='', market_phase=None):
    """新規シミュレーション銘柄に対して1ヶ月の3シナリオを生成（Claude使用）

    Args:
        sim: シミュレーション銘柄dict
        context_str: 分析レポートなどの追加コンテキスト
        market_phase: detect_phase()の返り値 {'phase': str, 'score': int, 'reasons': list}
    """
    ep = sim['entry_price']
    stop_pct = round((ep - sim['stop_loss']) / ep * 100, 1)
    target_pct = round((sim['target1'] - ep) / ep * 100, 1)

    # 機能1: フェーズ・マクロリスク情報をプロンプトに追加
    phase_str = ''
    bear_min_prob = 20  # デフォルトのbear最低確率
    if market_phase:
        phase = market_phase.get('phase', 'Steady')
        phase_score = market_phase.get('score', 0)
        phase_reasons = market_phase.get('reasons', [])
        phase_reasons_str = '\n'.join(phase_reasons[:3]) if phase_reasons else '（理由なし）'
        market_day_str = '平日（市場稼働日）' if IS_MARKET_DAY else '週末（市場休場）'
        phase_str = f"""
## 現在の市場環境（フェーズ・マクロリスク）
- 市場稼働: {market_day_str}
- 市場フェーズ: **{phase}**（スコア: {phase_score}）
- フェーズ判定根拠:
{phase_reasons_str}
- コンテキスト: {context_str[:300] if context_str else '（分析レポートなし）'}
"""
        # Defendフェーズ時はbear確率を最低35%に設定
        if phase == 'Defend':
            bear_min_prob = 35

    bear_min_note = f'bearの最低確率は{bear_min_prob}%以上にすること（現在フェーズ: {market_phase.get("phase", "Steady") if market_phase else "不明"}）。' if bear_min_prob > 20 else ''

    prompt = f"""以下の銘柄について、これから1ヶ月（20営業日）のシミュレーション追跡用に
強気・中立・弱気の3シナリオを立ててください。

銘柄: {sim['name']}（{sim['code']}）
エントリー価格: {ep}円  損切り: -{stop_pct}%  目標①: +{target_pct}%
RS26w: {sim.get('rs_26w','N/A')}  スコア: {sim.get('score','N/A')}/7
{phase_str}
## 確率設定の指示
- 現在のフェーズとマクロリスクを考慮して確率を設定すること
- {bear_min_note}
- Attackフェーズ時はbull確率を高め（35%以上）に設定すること
- Defendフェーズ時はbear確率を最低35%以上にすること（上記マクロリスク環境が深刻な場合は50%以上も検討）
- bull+base+bear の合計は必ず100にすること

## 出力（JSONのみ・説明文不要）
{{
  "bull": {{
    "label": "強気",
    "summary": "（シナリオ概要 30文字以内）",
    "w1_pct": 8.0,
    "w2_pct": 15.0,
    "w3_pct": 20.0,
    "w4_pct": 25.0,
    "trigger": "（成立条件 30文字以内）",
    "invalidation": "（崩壊条件 20文字以内）",
    "probability": 30
  }},
  "base": {{
    "label": "中立",
    "summary": "（シナリオ概要 30文字以内）",
    "w1_pct": 2.0,
    "w2_pct": 5.0,
    "w3_pct": 8.0,
    "w4_pct": 12.0,
    "trigger": "（成立条件 30文字以内）",
    "invalidation": "（崩壊条件 20文字以内）",
    "probability": 50
  }},
  "bear": {{
    "label": "弱気",
    "summary": "（シナリオ概要 30文字以内）",
    "w1_pct": -5.0,
    "w2_pct": -8.0,
    "w3_pct": -8.0,
    "w4_pct": -8.0,
    "trigger": "（成立条件 30文字以内）",
    "invalidation": "（崩壊条件 20文字以内）",
    "probability": 20
  }}
}}
注意: bull+base+bear の probability合計は必ず100にすること。w4_pctは損切り(-{stop_pct}%)〜目標(+{target_pct}%)の範囲内で設定。"""

    response = call_claude(prompt, max_tokens=800, inject_labels=False)
    try:
        import re as _re
        m = _re.search(r'\{[\s\S]*\}', response)
        if m:
            parsed = json.loads(m.group())
            # validate required keys
            for k in ('bull', 'base', 'bear'):
                if k not in parsed:
                    raise ValueError(f"missing scenario: {k}")
                for f in ('label', 'summary', 'w1_pct', 'w2_pct', 'w3_pct', 'w4_pct', 'probability'):
                    if f not in parsed[k]:
                        raise ValueError(f"missing field {f} in {k}")
            return parsed
    except Exception as e:
        print(f'  [警告] シナリオJSON解析失敗: {e}')
    # fallback: default scenarios
    return {
        'bull':  {'label': '強気', 'summary': 'RS継続上昇', 'w1_pct': 8.0,  'w2_pct': 15.0, 'w3_pct': 20.0, 'w4_pct': 25.0, 'trigger': 'ブレイクアウト継続', 'invalidation': 'SMA50割れ', 'probability': 30},
        'base':  {'label': '中立', 'summary': 'もみ合い継続', 'w1_pct': 2.0,  'w2_pct': 5.0,  'w3_pct': 8.0,  'w4_pct': 12.0, 'trigger': '市場落ち着き', 'invalidation': '出来高急減', 'probability': 50},
        'bear':  {'label': '弱気', 'summary': '調整・下落', 'w1_pct': -5.0, 'w2_pct': -8.0, 'w3_pct': -8.0, 'w4_pct': -8.0, 'trigger': '市場リスク増大', 'invalidation': '上昇転換', 'probability': 20},
    }


def _analyze_daily_deviation(sim, daily_entry, prev_hyp):
    """差異分析と翌日仮説をClaudeで生成"""
    scenarios = sim.get('scenarios', {})

    # 前日仮説との一致判定
    prev_direction = prev_hyp.get('next_day_direction', '') if prev_hyp else ''
    actual_direction = '上昇' if daily_entry['daily_pct'] > 0.3 else ('下落' if daily_entry['daily_pct'] < -0.3 else '横ばい')
    prev_match = (prev_direction == actual_direction) if prev_direction else None

    scenarios_str = json.dumps(scenarios, ensure_ascii=False, indent=2)

    prompt = f"""投資シミュレーション検証チームです。本日の値動きを分析してください。

銘柄: {sim['name']}（{sim['code']}）
エントリー: {sim['entry_price']}円 / {sim['start_date']} ({sim.get('days_elapsed',0)}営業日目)

【3シナリオ（現在確率）】
{scenarios_str}

【前日仮説】 方向={prev_direction or 'なし'} 根拠={prev_hyp.get('next_day_reason','') if prev_hyp else ''}
【実際】 価格={daily_entry['price']}円 本日={daily_entry['daily_pct']:+.1f}% 累計={daily_entry['cumulative_pct']:+.1f}%
【各シナリオとの乖離】 {daily_entry['scenario_gaps']}

JSONのみ返答（説明文不要）:
{{
  "cause": "[事実]または[AI分析]ラベルつきで差異原因50文字以内",
  "hypothesis_revision": "シナリオ修正点30文字以内（修正なしなら'修正なし'）",
  "updated_probabilities": {{"bull": 30, "base": 50, "bear": 20}},
  "next_day_direction": "上昇|下落|横ばい",
  "next_day_reason": "翌日方向の根拠40文字以内",
  "next_day_confidence": "高|中|低",
  "next_day_key_level": "注目価格水準"
}}
確率合計は必ず100にすること。"""

    response = call_claude(prompt, max_tokens=600, inject_labels=False)
    try:
        import re as _re
        m = _re.search(r'\{[\s\S]*\}', response)
        if m:
            result = json.loads(m.group())
            result['prev_match'] = prev_match
            return result
    except Exception as e:
        print(f'  [警告] 差異分析JSON解析失敗: {e}')

    return {
        'cause': '[AI分析] データ取得失敗',
        'hypothesis_revision': '修正なし',
        'updated_probabilities': {sid: scenarios[sid].get('probability', 33) for sid in scenarios} if scenarios else {'bull': 33, 'base': 34, 'bear': 33},
        'next_day_direction': '横ばい',
        'next_day_reason': 'データ不足',
        'next_day_confidence': '低',
        'next_day_key_level': '',
        'prev_match': prev_match,
    }


# ─── 機能2: セクター分散チェック ────────────────────────────────────────────────
def _get_sector_group(code_str: str, stock_data: dict = None) -> str:
    """
    銘柄コードからセクターグループを返す。
    stock_dataがあれば 'sector' / 'industry' フィールドを優先使用。
    なければコード番号範囲で簡易判定。
    """
    # データがあればsector/industryフィールドを優先
    if stock_data:
        sector = stock_data.get('sector') or stock_data.get('industry') or ''
        if sector:
            return sector

    # フィールドがなければコード番号範囲で簡易判定
    try:
        code_int = int(code_str)
        if 6200 <= code_int <= 6999:
            return '電機・精密機器・機械'
        elif 3000 <= code_int <= 3999:
            return '繊維・化学'
        elif 7000 <= code_int <= 7999:
            return '自動車・輸送'
        elif 1000 <= code_int <= 1999:
            return '農林・水産・鉱業・エネルギー'
        elif 2000 <= code_int <= 2999:
            return '食品・飲料'
        elif 4000 <= code_int <= 4999:
            return '医薬・バイオ'
        elif 5000 <= code_int <= 5999:
            return '鉄鋼・非鉄・建設・ガラス'
        elif 8000 <= code_int <= 8999:
            return '金融・不動産'
        elif 9000 <= code_int <= 9999:
            return '通信・インフラ・サービス'
        else:
            return 'その他'
    except (ValueError, TypeError):
        return 'その他'


def _check_sector_diversity(actives: list, candidate_code: str, stocks_by_code: dict) -> tuple:
    """
    セクター分散チェック: 同一セクターの銘柄が2件以上ある場合はFalseを返す。
    セクターはscreening dataの 'sector' or 'industry' フィールドを使用。
    なければ簡易判定（コード範囲: 6xxx=電機・機械, 3xxx=繊維・化学等）。

    Args:
        actives: 現在アクティブなシミュレーションリスト
        candidate_code: チェック対象の銘柄コード（str）
        stocks_by_code: {code: stock_data} のdict

    Returns:
        (bool: 追加可能か, str: 理由)
    """
    SECTOR_LIMIT = 2  # 同一セクター上限

    try:
        candidate_data = stocks_by_code.get(str(candidate_code), {})
        candidate_sector = _get_sector_group(str(candidate_code), candidate_data)

        # アクティブ銘柄の各セクターをカウント
        sector_counts = {}
        for active in actives:
            active_code = str(active.get('code', ''))
            active_data = stocks_by_code.get(active_code, {})
            sector = _get_sector_group(active_code, active_data)
            sector_counts[sector] = sector_counts.get(sector, 0) + 1

        current_count = sector_counts.get(candidate_sector, 0)
        if current_count >= SECTOR_LIMIT:
            reason = f'セクター「{candidate_sector}」はすでに{current_count}銘柄追跡中（上限: {SECTOR_LIMIT}銘柄）'
            print(f'    [セクター分散] 除外: {candidate_code} - {reason}')
            return False, reason

        return True, f'セクター「{candidate_sector}」は{current_count}銘柄（上限: {SECTOR_LIMIT}銘柄未満）→ 追加可能'
    except Exception as e:
        print(f'  [警告] セクター分散チェック失敗: {e}')
        return True, 'チェック失敗（デフォルト: 追加許可）'


# ─── 機能3: 週次シナリオ精度レビュー ─────────────────────────────────────────────
def _weekly_scenario_review(actives: list, history: list) -> str:
    """
    土曜日（DAY_MODE == 'saturday'）に実行する週次シナリオ精度レビュー。
    各追跡銘柄について week1（5営業日）の daily_log を集計し、
    実際の累積騰落率 vs 各シナリオの w1_pct を比較する。

    Args:
        actives: アクティブシミュレーションリスト
        history: 完了済みシミュレーションリスト

    Returns:
        markdown形式の週次レビュー文字列
    """
    print('  [週次レビュー] 土曜日: シナリオ精度レビュー生成中...')
    try:
        all_sims = actives + history
        review_lines = []
        scenario_lead_counts = {'bull': 0, 'base': 0, 'bear': 0}
        total_w1_entries = 0

        for sim in all_sims:
            daily_log = sim.get('daily_log', [])
            scenarios = sim.get('scenarios', {})
            if not daily_log or not scenarios:
                continue

            # week1（5営業日分）のdaily_logを取得
            w1_logs = [d for d in daily_log if isinstance(d, dict)][:5]
            if not w1_logs:
                continue

            # week1 実際の累積騰落率（最後のエントリ）
            actual_w1_pct = w1_logs[-1].get('cumulative_pct', 0)
            total_w1_entries += 1

            # 各シナリオのw1_pctとの差
            best_sid = None
            best_gap = float('inf')
            gaps_str_parts = []
            for sid in ('bull', 'base', 'bear'):
                scen = scenarios.get(sid, {})
                w1_target = scen.get('w1_pct', 0)
                gap = abs(actual_w1_pct - w1_target)
                gaps_str_parts.append(f"{sid}={w1_target:+.1f}%（差{gap:+.1f}%）")
                if gap < best_gap:
                    best_gap = gap
                    best_sid = sid

            if best_sid:
                scenario_lead_counts[best_sid] = scenario_lead_counts.get(best_sid, 0) + 1

            best_label = (scenarios.get(best_sid, {}).get('label', best_sid)) if best_sid else '不明'
            review_lines.append(
                f"- **{sim.get('name', '?')}**（{sim.get('code', '?')}）: "
                f"実績w1={actual_w1_pct:+.1f}% | {' / '.join(gaps_str_parts)} "
                f"→ **週次リードシナリオ: {best_label}**"
            )

        if not review_lines:
            return '\n## 週次シナリオ精度レビュー（土曜）\n\n（週1件以上のdaily_logデータがありません）\n'

        # シナリオ別リード回数サマリ
        bull_rate = scenario_lead_counts['bull'] / total_w1_entries * 100 if total_w1_entries else 0
        base_rate = scenario_lead_counts['base'] / total_w1_entries * 100 if total_w1_entries else 0
        bear_rate = scenario_lead_counts['bear'] / total_w1_entries * 100 if total_w1_entries else 0

        # Claudeでシナリオ確率更新提案を生成
        print('    [Claude] 週次シナリオ精度レビュー提案生成中...')
        detail_str = '\n'.join(review_lines)
        update_prompt = f"""投資シミュレーション検証チームです。今週（土曜）のシナリオ精度を振り返ってください。

## 週次シナリオ実績サマリ（追跡{total_w1_entries}銘柄）
{detail_str}

## シナリオ別 週次リード回数
- 強気（bull）リード: {scenario_lead_counts['bull']}件 ({bull_rate:.0f}%)
- 中立（base）リード: {scenario_lead_counts['base']}件 ({base_rate:.0f}%)
- 弱気（bear）リード: {scenario_lead_counts['bear']}件 ({bear_rate:.0f}%)

以下の点を簡潔に分析してください（200文字以内）:
1. 今週最も的中したシナリオパターンと理由
2. 来週のシナリオ確率設定への反映提案（例: bear確率を+5%調整）
3. 改善ポイント（シナリオ設計・確率設定の課題）

[AI分析]ラベルを付けて回答してください。"""

        try:
            claude_suggestion = call_claude(update_prompt, max_tokens=500, inject_labels=False)
        except Exception as e:
            claude_suggestion = f'[AI分析] 提案生成失敗: {e}'

        md = f"""
## 週次シナリオ精度レビュー（土曜: {TODAY}）

### 銘柄別 Week1 実績 vs シナリオ
{chr(10).join(review_lines)}

### シナリオ別リード回数（計{total_w1_entries}銘柄）
| シナリオ | リード回数 | 比率 |
|---------|----------|------|
| 強気（bull） | {scenario_lead_counts['bull']}件 | {bull_rate:.0f}% |
| 中立（base） | {scenario_lead_counts['base']}件 | {base_rate:.0f}% |
| 弱気（bear） | {scenario_lead_counts['bear']}件 | {bear_rate:.0f}% |

### Claude提案（確率設定の改善案）
{claude_suggestion}
"""
        print(f'    [週次レビュー] 完了 ({total_w1_entries}銘柄分析)')
        return md

    except Exception as e:
        print(f'  [警告] 週次シナリオ精度レビュー失敗: {e}')
        return f'\n## 週次シナリオ精度レビュー（土曜）\n\n（レビュー生成失敗: {e}）\n'


