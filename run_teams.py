#!/usr/bin/env python3
"""Investment Team System — 9 チーム自動実行エントリポイント。

実体は `teams/` パッケージに分割されており、本ファイルは dispatch のみ担う。
使い方:
    python run_teams.py              # 全チーム順次実行
    python run_teams.py <team_key>   # 単一チーム実行（例: info / strategy / verification）

外部スクリプト・テストからの `from run_teams import X` も後方互換として維持。
"""
import sys

# ── runtime context（ANTHROPIC_API_KEY 必須） ──
from teams._context import (
    JST, NOW_JST, TODAY, WEEKDAY, IS_MARKET_DAY,
    DAY_MODE, DAY_LABEL, DAY_FOCUS,
    DATA_DIR, REPORT_DIR,
    client, MODEL, GEMINI_KEY, GEMINI_URL,
)

# ── 後方互換: 旧コードが `from run_teams import X` で参照する名前 ──
from teams._config import TEAM_KPIS, SOURCE_RELIABILITY
from teams._base import (
    call_claude, call_gemini, save_source_log,
    load_json, _fetch_fresh_price,
    read_report, is_generated, screen_to_list, _score_num, _rs26w, write_report,
    save_kpi_log, build_kpi_check_prompt,
    read_shared_context, update_shared_context, get_feedback_prefix,
    read_knowledge, write_knowledge,
    LABEL_RULE, SHARED_CTX_PATH, KNOWLEDGE_DIR,
)
from teams._tools import (
    AGENT_TOOLS, _execute_tool, _agent_system_prompt, _run_agent_team,
)
from teams._phase import detect_phase
from teams._scenarios import (
    MAX_SIM_SLOTS,
    _make_new_sim, _get_week_target, _determine_leading_scenario,
    _scenario_gaps, _generate_scenarios, _analyze_daily_deviation,
    _get_sector_group, _check_sector_diversity, _weekly_scenario_review,
)

# ── チーム定義（dispatch の source of truth） ──
from teams import TEAMS, TEAM_REPORT_MAP


def _dispatch_all() -> None:
    """全チームを順次実行し、各チーム完了後に shared_context を更新する。"""
    SHARED_CTX_PATH.write_text(
        f'# shared_context.md（{TODAY}更新）\n'
        '全チームの結論・重要情報を共有するハブ。各チームは必ずこの情報を参照すること。\n',
        encoding='utf-8',
    )
    for key, (name, fn) in TEAMS.items():
        print(f'\n[{name}] 開始...')
        try:
            fn()
            report_name = TEAM_REPORT_MAP.get(key)
            if report_name:
                summary = read_report(report_name)[:400].replace('\n', ' ').strip()
                update_shared_context(name, summary)
            print(f'[{name}] 完了')
        except Exception as e:
            print(f'[{name}] エラー: {e}', file=sys.stderr)


def _dispatch_one(key: str) -> None:
    """単一チームを実行し、shared_context を更新する。"""
    name, fn = TEAMS[key]
    print(f'[{name}] 開始...')
    fn()
    report_name = TEAM_REPORT_MAP.get(key)
    if report_name:
        summary = read_report(report_name)[:400].replace('\n', ' ').strip()
        update_shared_context(name, summary)
    print(f'[{name}] 完了')


if __name__ == '__main__':
    target = sys.argv[1] if len(sys.argv) > 1 else 'all'
    if target == 'all':
        _dispatch_all()
    elif target in TEAMS:
        _dispatch_one(target)
    else:
        print(f'不明なチーム: {target}')
        print(f'使用可能: {list(TEAMS.keys())} または all')
        sys.exit(1)
