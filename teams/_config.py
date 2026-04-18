"""チーム共通の静的設定: KPI 定義と情報源信頼性スコア。

env に依存しない純粋データのみ。runtime context は `_context.py`。
"""
from __future__ import annotations


# ─── チーム別KPI定義（全チーム共通の評価基準） ────────────────────
TEAM_KPIS = {
    '情報収集チーム': {
        'description': '市場情報を正確・迅速に収集し、後続チームに届ける',
        'kpis': [
            {'id': 'info_coverage',    'what': '必須8項目の網羅率',         'target': '100%',     'how': '指数/為替/債券/コモディティ/イベント/セクター/ニュース/RS上位が全て記載されているか'},
            {'id': 'info_accuracy',    'what': 'データ誤り件数',             'target': '0件/日',   'how': 'スクリーニング数値と実際のGemini取得値が整合しているか'},
            {'id': 'source_quality',   'what': '信頼度4以上ソース比率',      'target': '70%以上',  'how': 'source_log.md の reliability≥4 件数 / 全件数'},
            {'id': 'source_count',     'what': '情報源数',                   'target': '3件以上',  'how': 'Gemini groundingChunks の件数'},
        ]
    },
    '銘柄選定・仮説チーム': {
        'description': 'Aランク銘柄を正確に選定し、判断理由を明示する',
        'kpis': [
            {'id': 'a_rank_win_rate',  'what': 'Aランク銘柄の2週間後勝率',  'target': '60%以上',  'how': 'シミュレーション追跡・検証チームがシミュレーションで追跡・集計'},
            {'id': 'rs_retention',     'what': 'Aランク選定銘柄のRS維持率', 'target': '70%以上',  'how': '2週後もRS26w上位30%以内を維持している割合'},
            {'id': 'reason_quality',   'what': '判断理由の具体性',           'target': '根拠3つ以上/銘柄', 'how': 'テクニカル/ファンダ/RS の3軸で根拠が記載されているか'},
            {'id': 'stock_count',      'what': '評価銘柄数',                 'target': '5銘柄以上/日', 'how': 'A/B/Cランク合計の評価銘柄数'},
        ]
    },
    'リスク管理チーム': {
        'description': '資産を守り、ルールベースのリスク管理を徹底する',
        'kpis': [
            {'id': 'dd_compliance',    'what': 'DD許容上限遵守',             'target': '-10%以内', 'how': 'ポートフォリオ全体のドローダウンが-20万円を超えていないか'},
            {'id': 'stoploss_coverage','what': '損切りライン設定率',          'target': '保有全銘柄100%', 'how': '各保有銘柄に損切り価格が設定・記載されているか'},
            {'id': 'sector_limit',     'what': 'セクター集中度',             'target': '30%以内',  'how': '最大セクターの資産占有率が30%を超えていないか'},
            {'id': 'alert_accuracy',   'what': '警告的中率（累積）',         'target': '60%以上',  'how': '過去の警告銘柄が実際に下落した割合（kpi_log.jsonで追跡）'},
        ]
    },
    '投資戦略チーム': {
        'description': '市場フェーズを正確に判定し、具体的なエントリー計画を立案する',
        'kpis': [
            {'id': 'phase_accuracy',   'what': 'フェーズ判定精度',           'target': '70%以上',  'how': '翌週の市場動向と当日判定（Attack/Steady/Defend）が一致した割合'},
            {'id': 'entry_win_rate',   'what': 'エントリー後2週間勝率',      'target': '50%以上',  'how': 'シミュレーション追跡・検証チームが追跡。エントリー推奨銘柄が2週後に利益圏にある割合'},
            {'id': 'rr_ratio',         'what': '平均RR比',                   'target': '3.0以上',  'how': '各エントリー候補の（目標-エントリー）/（エントリー-損切り）の平均'},
            {'id': 'plan_concreteness','what': 'アクションプランの具体性',   'target': '銘柄/価格/理由を全て明記', 'how': 'エントリー候補テーブルに銘柄名・コード・価格・損切り・目標・RR比・根拠が記載されているか'},
        ]
    },
    'レポート統括': {
        'description': '全チーム情報を統合し、読みやすい日次レポートを作成する',
        'kpis': [
            {'id': 'integration_rate', 'what': '全チームレポート統合率',     'target': '100%',     'how': '情報収集/分析/リスク/戦略の4チームの内容が全て含まれているか'},
            {'id': 'next_day_points',  'what': '翌日注目点の明記',           'target': '必須3件以上', 'how': '「来週以降の注目点」または「翌日の注目点」セクションに3件以上あるか'},
            {'id': 'fact_ai_label',    'what': '[事実]/[AI分析]ラベル遵守', 'target': '100%',     'how': 'レポート内の全セクションに[事実]または[AI分析]ラベルが付いているか'},
        ]
    },
    'セキュリティチーム': {
        'description': 'コードとシステムの安全性を監視し、脅威を早期検知する',
        'kpis': [
            {'id': 'critical_zero',    'what': '重大脆弱性の未報告ゼロ',     'target': '0件',      'how': 'CRITICAL/HIGH相当の脆弱性が発見された場合、必ず報告されているか'},
            {'id': 'code_review',      'what': 'コードレビュー実施',         'target': '週1回以上', 'how': '直近7日間でrun_teams.py/index.htmlのレビューを実施したか'},
            {'id': 'threat_freshness', 'what': '脅威情報の鮮度',             'target': '当日情報を含む', 'how': 'Geminiが収集した脅威情報に当日（{TODAY}）の日付が含まれているか'},
        ]
    },
    '内部監査チーム': {
        'description': '全チームのKPI達成状況を評価し、改善サイクルを推進する',
        'kpis': [
            {'id': 'audit_coverage',   'what': '全チーム評価完了率',         'target': '100%',     'how': '全チームに対して評価スコアが付いているか'},
            {'id': 'improvement_count','what': '改善提案数',                 'target': '2件以上/日', 'how': '優先度「高」または「中」の改善提案が合計2件以上あるか'},
            {'id': 'followup_rate',    'what': '前回提案フォローアップ率',   'target': '100%',     'how': '前回の改善提案に対して今回の評価で言及しているか'},
            {'id': 'pdca_cycle',       'what': 'PDCA回転数',                 'target': '週4回以上', 'how': '過去7日間でaudit_log.mdへの書き込みが4回以上あるか'},
        ]
    },
    'シミュレーション追跡・検証チーム': {
        'description': 'シミュレーション追跡と差異分析により、全チームの予測精度を向上させる',
        'kpis': [
            {'id': 'sim_direction',    'what': 'シミュレーション方向一致率', 'target': '50%→60%（成長目標）', 'how': '予測した上昇/下落方向と実際の結果が一致した割合'},
            {'id': 'analysis_complete','what': '差異分析完了率',             'target': '100%',     'how': '追跡終了した全シミュレーションに原因分析が付いているか'},
            {'id': 'kpi_check',        'what': 'KPI自動チェック実施',        'target': '毎日',     'how': 'kpi_log.jsonに当日分の記録があるか'},
            {'id': 'feedback_count',   'what': '他チームへのフィードバック数', 'target': '1件以上/週', 'how': '銘柄選定・仮説チーム・投資戦略チームへの改善フィードバックが週1件以上あるか'},
        ]
    },
}


# 信頼性スコア定義（ドメインベース）
SOURCE_RELIABILITY = {
    'nikkei.com': ('日経新聞', 5), 'reuters.com': ('Reuters', 5),
    'bloomberg.com': ('Bloomberg', 5), 'wsj.com': ('WSJ', 5),
    'minkabu.jp': ('みんかぶ', 4), 'kabutan.jp': ('株探', 4),
    'finance.yahoo.co.jp': ('Yahoo!ファイナンス', 4),
    'investing.com': ('Investing.com', 4), 'tradingview.com': ('TradingView', 4),
    'oanda.jp': ('OANDA', 3), 'diamond.jp': ('ダイヤモンド', 4),
}
