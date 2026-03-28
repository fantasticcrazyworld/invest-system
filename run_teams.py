#!/usr/bin/env python3
"""
Investment Team System - GitHub Actions runner
各チームがClaude/Gemini APIを呼び出してレポートを生成する
"""
import anthropic
import json
import os
import sys
import requests
from datetime import datetime, timezone, timedelta
from pathlib import Path

JST = timezone(timedelta(hours=9))
TODAY = datetime.now(JST).strftime('%Y-%m-%d')
DATA_DIR = Path(os.environ.get('INVEST_DATA_DIR', 'invest-data'))
REPORT_DIR = Path('reports') / 'daily'
REPORT_DIR.mkdir(parents=True, exist_ok=True)

client = anthropic.Anthropic(api_key=os.environ['ANTHROPIC_API_KEY'])
MODEL = 'claude-sonnet-4-6'
GEMINI_KEY = os.environ.get('GEMINI_API', '')
GEMINI_URL = 'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent'

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
    '分析チーム': {
        'description': 'Aランク銘柄を正確に選定し、判断理由を明示する',
        'kpis': [
            {'id': 'a_rank_win_rate',  'what': 'Aランク銘柄の2週間後勝率',  'target': '60%以上',  'how': '検証チームがシミュレーションで追跡・集計'},
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
            {'id': 'entry_win_rate',   'what': 'エントリー後2週間勝率',      'target': '50%以上',  'how': '検証チームが追跡。エントリー推奨銘柄が2週後に利益圏にある割合'},
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
    '検証チーム': {
        'description': 'シミュレーション追跡と差異分析により、全チームの予測精度を向上させる',
        'kpis': [
            {'id': 'sim_direction',    'what': 'シミュレーション方向一致率', 'target': '50%→60%（成長目標）', 'how': '予測した上昇/下落方向と実際の結果が一致した割合'},
            {'id': 'analysis_complete','what': '差異分析完了率',             'target': '100%',     'how': '追跡終了した全シミュレーションに原因分析が付いているか'},
            {'id': 'kpi_check',        'what': 'KPI自動チェック実施',        'target': '毎日',     'how': 'kpi_log.jsonに当日分の記録があるか'},
            {'id': 'feedback_count',   'what': '他チームへのフィードバック数', 'target': '1件以上/週', 'how': '分析チーム・投資戦略チームへの改善フィードバックが週1件以上あるか'},
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


def call_claude(prompt: str, max_tokens: int = 4096) -> str:
    msg = client.messages.create(
        model=MODEL,
        max_tokens=max_tokens,
        messages=[{'role': 'user', 'content': prompt}]
    )
    return msg.content[0].text


def call_gemini(prompt: str) -> tuple[str, list[dict]]:
    """Gemini with Google Search grounding。(text, sources) を返す"""
    if not GEMINI_KEY:
        return '（Gemini APIキー未設定）', []
    payload = {
        'contents': [{'parts': [{'text': prompt}]}],
        'tools': [{'google_search': {}}],
    }
    resp = requests.post(f'{GEMINI_URL}?key={GEMINI_KEY}', json=payload, timeout=60)
    data = resp.json()
    candidate = (data.get('candidates') or [{}])[0]
    text = (candidate.get('content', {}).get('parts') or [{}])[0].get('text', '')
    # grounding sources
    sources = []
    for chunk in candidate.get('groundingMetadata', {}).get('groundingChunks', []):
        web = chunk.get('web', {})
        uri = web.get('uri', '')
        title = web.get('title', uri)
        if uri:
            domain = uri.split('/')[2] if uri.startswith('http') else uri
            rel_name, rel_score = SOURCE_RELIABILITY.get(domain, ('その他', 3))
            sources.append({'title': title, 'url': uri, 'source': rel_name, 'reliability': rel_score})
    return text, sources


def save_source_log(team: str, sources: list[dict], raw_text: str = ''):
    """情報源ログを reports/source_log.md に追記（レポートには含まない）"""
    log_path = REPORT_DIR / 'source_log.md'
    existing = log_path.read_text(encoding='utf-8') if log_path.exists() else f'# 情報源ログ\n'
    lines = [f'\n## {TODAY} - {team}']
    if sources:
        lines.append('| 情報源 | 信頼性 | URL |')
        lines.append('|--------|--------|-----|')
        for s in sources:
            stars = '★' * s['reliability'] + '☆' * (5 - s['reliability'])
            short_url = s['url'][:60] + '...' if len(s['url']) > 60 else s['url']
            lines.append(f"| {s['title'][:30]} ({s['source']}) | {stars} | {short_url} |")
    else:
        lines.append('（情報源なし）')
    log_path.write_text(existing + '\n'.join(lines) + '\n', encoding='utf-8')
    print(f'  -> source_log.md 更新 ({len(sources)}件)')


def load_json(filename: str, default=None):
    path = DATA_DIR / filename
    if path.exists():
        try:
            return json.loads(path.read_text(encoding='utf-8'))
        except Exception:
            pass
    return default if default is not None else {}


def read_report(name: str) -> str:
    path = REPORT_DIR / f'{name}.md'
    return path.read_text(encoding='utf-8') if path.exists() else '（未生成）'


def write_report(name: str, content: str):
    path = REPORT_DIR / f'{name}.md'
    path.write_text(content, encoding='utf-8')
    print(f'  -> {path}')


def save_kpi_log(kpi_results: dict):
    """KPI達成状況を kpi_log.json に追記（日次トレンド分析用）"""
    log_path = REPORT_DIR / 'kpi_log.json'
    existing = []
    if log_path.exists():
        try:
            existing = json.loads(log_path.read_text(encoding='utf-8'))
        except Exception:
            pass
    # 当日分を上書き or 追加
    existing = [e for e in existing if e.get('date') != TODAY]
    existing.append({'date': TODAY, 'teams': kpi_results})
    # 直近90日分だけ保持
    existing = existing[-90:]
    log_path.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'  -> kpi_log.json 更新')


def build_kpi_check_prompt() -> str:
    """内部監査用: 全チームKPI一覧をテキストに変換"""
    lines = ['## 各チームのKPI定義']
    for team, info in TEAM_KPIS.items():
        lines.append(f'\n### {team}')
        lines.append(f'ミッション: {info["description"]}')
        lines.append('| ID | 何を測る | 目標値 | 評価方法 |')
        lines.append('|----|---------|--------|---------|')
        for k in info['kpis']:
            lines.append(f'| {k["id"]} | {k["what"]} | {k["target"]} | {k["how"]} |')
    return '\n'.join(lines)


# ─── Team 1: 情報収集 ────────────────────────────────────────────
def run_info_gathering():
    screen = load_json('screen_full_results.json', [])
    stocks = screen if isinstance(screen, list) else []
    total = len(stocks)
    top = sorted(
        [s for s in stocks if isinstance(s, dict)],
        key=lambda x: x.get('rs_26w', 0), reverse=True
    )[:10]
    top_str = '\n'.join(
        f"  {s.get('code','?')} {s.get('name','')}: RS26w={s.get('rs_26w','?')}, score={s.get('score','?')}"
        for s in top
    )

    # ── Step1: Gemini (Google Search) で最新市場情報を収集 ──
    print('  [Gemini] 市場情報収集中...')
    g_prompt = f"""{TODAY} の最新市場情報を収集してください。

以下を正確な数値で答えてください（最新の終値・速報値）:
1. 日経平均・TOPIX・マザーズ の終値と前日比（%）
2. S&P500・NASDAQ・ダウ の終値と前日比（%）
3. ドル円・ユーロ円 の現在値
4. 米10年債利回り・日本10年債利回り
5. WTI原油・金 の現在値
6. 本日〜今週の重要経済イベント（日時・内容・予想値）
7. 昨日のS&P500セクター別騰落ランキング（全11セクター）
8. 日本株・米国株で昨日特に話題になったニュース3件
"""
    gemini_text, sources = call_gemini(g_prompt)
    save_source_log('情報収集チーム', sources, gemini_text)

    # ── Step2: Claude で構造化レポートに整形 ──
    prompt = f"""あなたは投資チームの「情報収集チーム」です。
Geminiが収集した最新市場情報を元に、本日 {TODAY} のレポートを作成してください。

## Geminiが収集した最新情報
{gemini_text}

## スクリーニングデータ（自動取得済み）
スキャン銘柄数: {total}
RS26w上位10銘柄:
{top_str}

## 出力フォーマット（必ずこの形式で）
# 情報収集チーム レポート
日付: {TODAY}

## 市場概況
（表形式: 指数・終値・前日比）

## 為替・コモディティ
| 項目 | 現在値 | 動向 |
...

## 金利
| 項目 | 水準 | 動向 |
...

## 本日の注目イベント
（日時・内容・予想値・注目理由）

## セクター動向（S&P500）
（上昇・下落ランキング）

## 注目ニュース
1. ...
2. ...
3. ...

## スクリーニング状況
スキャン: {total}銘柄 / RS上位10銘柄（上記データを整理して記載）
"""
    write_report('info_gathering', call_claude(prompt))


# ─── Team 2: 分析 ────────────────────────────────────────────────
def run_analysis():
    screen = load_json('screen_full_results.json', [])
    stocks = screen if isinstance(screen, list) else []
    top20 = sorted(
        [s for s in stocks if isinstance(s, dict) and s.get('score', 0) >= 6],
        key=lambda x: x.get('rs_26w', 0), reverse=True
    )[:20]
    info_report = read_report('info_gathering')

    # 上位10銘柄の銘柄名リストを作成
    top10_names = [f"{s.get('code')} {s.get('name','')}" for s in top20[:10]]
    names_str = '・'.join(top10_names)

    # ── Step1: Gemini で各銘柄の最新ニュース・業績・材料を収集 ──
    print('  [Gemini] 銘柄情報収集中...')
    g_prompt = f"""以下の日本株 {len(top10_names)} 銘柄について、最新情報を収集してください。

対象銘柄: {names_str}

各銘柄について以下を調べてください:
1. 直近の決算結果（売上・営業利益の前年比成長率）
2. 直近のニュース・材料（ポジティブ/ネガティブ）
3. アナリストの評価・目標株価（あれば）
4. 株価の最近の動き（上昇トレンド中か、調整中か）
5. 業界全体の動向（追い風・逆風）

事実のみを記載し、情報が見つからない場合はその旨を明記してください。
"""
    gemini_text, sources = call_gemini(g_prompt)
    save_source_log('分析チーム', sources, gemini_text)

    # ── Step2: Claude でテクニカル＋ファンダを統合分析 ──
    prompt = f"""あなたは投資チームの「分析チーム」です。本日 {TODAY} の銘柄分析を行ってください。

## 情報収集チームのレポート
{info_report[:1200]}

## スクリーニング通過銘柄（スコア6以上、RS上位20件）
{json.dumps(top20, ensure_ascii=False, indent=2)[:2500]}

## Geminiが収集した各銘柄の最新情報（決算・ニュース・材料）
{gemini_text}

## 分析基準
ミネルヴィニのStage-2成長株投資基準:
- テクニカル: 株価>SMA50>SMA150>SMA200、SMA200上昇中、52週高値の75%以上
- RS: RS26wがプラスかつ高水準
- ファンダ: 売上・利益が前年比20%以上成長、EPS加速
- 需給: 出来高を伴うブレイクアウト

## ランク定義
- A: 全条件を満たす最優先候補（エントリー検討）
- B: 大半の条件を満たす（ウォッチ継続）
- C: 条件不足または様子見

## 出力フォーマット（必ずこの形式で）
# 分析チーム レポート
日付: {TODAY}

## 市場環境評価
（現在の市場がミネルヴィニ戦略に適しているか）

## 銘柄別分析

### Aランク（エントリー候補）
#### [銘柄名]（コード）
- **テクニカル判断**: （移動平均の並び・RSの状態・チャート形状）
- **ファンダ判断**: （売上/利益成長率・EPS傾向）
- **最新材料**: （Gemini情報より）
- **ランクA判定理由**: （具体的な根拠を箇条書き）
- **リスク要因**: （懸念点）

### Bランク（ウォッチ継続）
#### [銘柄名]（コード）
- **テクニカル判断**: ...
- **ファンダ判断**: ...
- **最新材料**: ...
- **ランクB判定理由**: （Aにならない理由を明記）

### Cランク（様子見）
（銘柄名・コードと一言理由のみ）

## 注目パターン
（VCP・カップウィズハンドル・フラットベース等）

## 総合所見
（分析チームとしての本日のまとめ）
"""
    write_report('analysis', call_claude(prompt, max_tokens=6000))


# ─── Team 3: リスク管理 ──────────────────────────────────────────
def run_risk_management():
    portfolio = load_json('portfolio.json', {})
    info_report = read_report('info_gathering')
    analysis_report = read_report('analysis')

    # 保有銘柄リストを作成
    pf_stocks = []
    if isinstance(portfolio, dict):
        pf_stocks = [f"{k} {v.get('name','')}" for k, v in portfolio.items() if k != '__meta__']
    elif isinstance(portfolio, list):
        pf_stocks = [f"{s.get('code','')} {s.get('name','')}" for s in portfolio]

    # ── Step1: Gemini で保有銘柄の最新リスク情報を収集 ──
    print('  [Gemini] リスク情報収集中...')
    if pf_stocks:
        g_prompt = f"""以下の保有銘柄について、投資家が注意すべきリスク情報を収集してください。

保有銘柄: {', '.join(pf_stocks[:10])}

各銘柄について:
1. 直近のネガティブニュース・下落材料
2. 決算ミス・業績下方修正の情報
3. 規制・訴訟・不祥事リスク
4. セクター全体の逆風要因
5. 地政学リスクの影響度

また、本日 {TODAY} の市場全体のリスク要因も列挙してください（VIX水準・信用スプレッド・マクロリスク）。
"""
        gemini_text, sources = call_gemini(g_prompt)
        save_source_log('リスク管理チーム', sources, gemini_text)
    else:
        gemini_text = '（保有銘柄なし）'

    # ── Step2: Claude でリスク評価レポートを作成 ──
    prompt = f"""あなたは投資チームの「リスク管理チーム」です。本日 {TODAY} のリスク評価を行ってください。

## 情報収集チームのレポート
{info_report[:1000]}

## 分析チームのレポート
{analysis_report[:800]}

## 現在のポートフォリオデータ
{json.dumps(portfolio, ensure_ascii=False, indent=2)[:2000]}

## Geminiが収集した最新リスク情報
{gemini_text}

## 評価基準
- 損切りライン: 買値の-7〜8%（ミネルヴィニルール）
- 最大ドローダウン許容: 総資産の-10%
- セクター集中上限: 1セクターに資産の30%まで
- 現金比率目標: Defend時50%以上、Steady時20〜30%

## 出力フォーマット（必ずこの形式で）
# リスク管理チーム レポート
日付: {TODAY}

## ポートフォリオ概況
- 保有銘柄数: X / 現金比率: X%

## リスク指標
| 項目 | 現状 | 警戒水準 | 評価 |
|------|------|----------|------|
| 最大含み損率 | % | -7% | ✅/⚠️/❌ |
| ドローダウン | % | -10% | ✅/⚠️/❌ |
| セクター集中度 | % | 30% | ✅/⚠️/❌ |
...

## 保有銘柄リスク評価
（各銘柄の損切りラインまでの距離・最新リスク材料）

## 市場リスク
（地政学・マクロ・VIX等 Gemini情報より）

## 損切り/縮小候補
（銘柄・理由・推奨アクションを明記）

## 推奨アクション（優先順）
1. ...
2. ...
"""
    write_report('risk', call_claude(prompt))


# ─── Team 4: 投資戦略 ────────────────────────────────────────────
def run_strategy():
    info_report = read_report('info_gathering')
    analysis_report = read_report('analysis')
    risk_report = read_report('risk')

    # ── Step1: Gemini でエントリータイミング・市場センチメントを調査 ──
    print('  [Gemini] 市場センチメント・タイミング調査中...')
    g_prompt = f"""{TODAY} の投資タイミングを判断するための情報を収集してください。

1. 機関投資家・ヘッジファンドの最新ポジション動向（COTレポート等）
2. 日本株市場の需給動向（外国人・個人・信託の売買動向）
3. 信用買い残・信用売り残の水準
4. Put/Call比率・VIX・Fear&Greedインデックス
5. 機関投資家の注目テーマ・セクターローテーション動向
6. 今週のIPO・大型PO予定（需給への影響）
7. 米国市場のマネーフロー（資金がどのセクターに向かっているか）
8. テクニカル的な重要サポート・レジスタンス水準（日経平均・S&P500）
"""
    gemini_text, sources = call_gemini(g_prompt)
    save_source_log('投資戦略チーム', sources, gemini_text)

    # ── Step2: Claude で戦略立案 ──
    prompt = f"""あなたは投資チームの「投資戦略チーム」です。本日 {TODAY} の投資戦略を策定してください。

## 情報収集チーム レポート
{info_report[:1000]}

## 分析チーム レポート（Aランク銘柄を重視）
{analysis_report[:1500]}

## リスク管理チーム レポート
{risk_report[:1000]}

## Geminiが収集した市場センチメント・需給情報
{gemini_text}

## 判定基準
- Attack: 市場トレンド上向き、RS上位銘柄が続々ブレイク、VIX低位安定
- Steady: トレンド中立、選別的エントリー可能
- Defend: 市場下落トレンド、現金保有が最優先

## 出力フォーマット（必ずこの形式で）
# 投資戦略チーム レポート
日付: {TODAY}

## 市場環境判定: [Attack/Steady/Defend]
**判定理由**:
- 根拠1: ...
- 根拠2: ...
- 根拠3: ...

## 需給・センチメント評価
（Gemini情報より: 機関動向・信用残・VIX等）

## 新規エントリー候補
| 銘柄 | コード | エントリー価格 | 損切り | 目標 | RR比 | 推奨サイズ | 根拠 |
|------|--------|--------------|--------|------|------|-----------|------|
...

## エントリー見送り理由
（Aランク銘柄でもエントリーしない場合、その理由を明記）

## 既存ポジション管理
（利確・損切り・ホールド継続の判断と理由）

## 本日のアクションプラン（優先順）
1. ...
2. ...

## 来週以降の注目点
...
"""
    write_report('strategy', call_claude(prompt, max_tokens=5000))


# ─── Team 5: レポート統括 ─────────────────────────────────────────
def run_daily_report():
    info = read_report('info_gathering')
    analysis = read_report('analysis')
    risk = read_report('risk')
    strategy = read_report('strategy')

    # ── Step1: Gemini で翌日の注目点・アフター情報を追加収集 ──
    print('  [Gemini] 翌日以降の注目情報収集中...')
    g_prompt = f"""{TODAY} 以降の投資家が注目すべき情報を収集してください。

1. 明日・今週中に予定されている主要決算発表（日米）
2. 明日以降の経済指標発表スケジュールと市場予想
3. 本日の市場引け後に発表されたニュース・決算速報
4. 明日の日本市場の注目点（先物・ADR動向）
5. 今週の重要なFRB高官発言予定
"""
    gemini_text, sources = call_gemini(g_prompt)
    save_source_log('レポート統括', sources, gemini_text)

    # ── Step2: Claude で統合レポート作成 ──
    prompt = f"""あなたは「レポート統括」です。全チームのレポートとGeminiの追加情報を統合し、
読みやすい日次レポートを作成してください。

## 情報収集チーム
{info[:1500]}

## 分析チーム
{analysis[:2000]}

## リスク管理チーム
{risk[:1200]}

## 投資戦略チーム
{strategy[:1500]}

## Geminiが収集した翌日以降の注目情報
{gemini_text}

## 出力フォーマット（必ずこの形式で）
# 📊 デイリー投資レポート {TODAY}

## エグゼクティブサマリー
（本日の要点を3〜5行で。市場環境判定と最重要アクションを必ず含める）

## 市場環境: [Attack/Steady/Defend]
（指数動向・センチメント・判定理由）

## 本日のアクションプラン
1. **[最優先]** ...（理由: ...）
2. ...
3. ...

## 注目銘柄サマリー
| ランク | 銘柄 | コード | ポイント |
|--------|------|--------|---------|
| A | ... | ... | ... |
...

## リスク警戒事項
（今すぐ対応が必要なもの）

## 明日以降の注目スケジュール
（Gemini情報より）

## 各チーム詳細
### 情報収集チーム
（要約200字以内）
### 分析チーム
（要約200字以内）
### リスク管理チーム
（要約200字以内）
### 投資戦略チーム
（要約200字以内）

---
Generated by Investment Team System (Claude + Gemini)
"""
    result = call_claude(prompt, max_tokens=5000)
    write_report(f'{TODAY}_daily_report', result)
    write_report('latest_report', result)


# ─── Team 6: セキュリティ ─────────────────────────────────────────
def run_security():
    import subprocess
    git_log = subprocess.run(
        ['git', 'log', '--oneline', '-20'],
        capture_output=True, text=True
    ).stdout

    # ── Step1: Gemini で最新のセキュリティ脅威・脆弱性情報を収集 ──
    print('  [Gemini] セキュリティ脅威情報収集中...')
    g_prompt = f"""{TODAY} の最新サイバーセキュリティ・金融システムセキュリティ情報を収集してください。

1. 金融・投資システムを狙った最新サイバー攻撃・フィッシング事例
2. Python/GitHub Actions/Vercel に関する最新脆弱性（CVE情報）
3. APIキー漏洩・クレデンシャル流出に関する最新インシデント事例
4. 個人投資家を狙った詐欺・セキュリティ被害の最新情報
5. anthropic/google AI API に関するセキュリティアドバイザリ
"""
    gemini_text, sources = call_gemini(g_prompt)
    save_source_log('セキュリティチーム', sources, gemini_text)

    # ── Step2: Claude でコード監査＋レポート作成 ──
    prompt = f"""あなたは「情報セキュリティチーム」です。本日 {TODAY} のセキュリティ監査を行ってください。

## Gitコミット履歴（直近20件）
{git_log}

## Geminiが収集した最新セキュリティ脅威情報
{gemini_text}

## 内部チェック項目
1. コミットメッセージに `key`, `secret`, `password`, `token` が含まれていないか
2. index.htmlに外部CDNスクリプトが追加されていないか（プロジェクトルールで禁止）
3. APIキーがハードコードされていないか（`sk-`, `AIza`, `Bearer`パターン）
4. Vercel serverless関数（api/claude.js, api/gemini.js）の実装に問題がないか
5. GitHub Actions workflowにシークレット漏洩リスクがないか

## 既知の安全設計（False Positive除外）
- APIキーはVercel環境変数で管理（サーバーサイド）
- Gemini APIキーはHTTPヘッダーで送らない（CORS対策）
- ANTHROPIC_API_KEY / GEMINI_API はGitHub Secrets + Vercel Env Varsで管理

## 出力フォーマット（必ずこの形式で）
# 情報セキュリティチーム レポート
日付: {TODAY}

## 総合評価: [GREEN / YELLOW / RED]

## 内部監査結果
| 項目 | 状態 | 詳細 |
|------|------|------|
| コミット履歴 | ✅/⚠️/❌ | ... |
| CDNスクリプト | ✅/⚠️/❌ | ... |
| APIキー露出 | ✅/⚠️/❌ | ... |
| Vercelプロキシ | ✅/⚠️/❌ | ... |
| GitHub Actions | ✅/⚠️/❌ | ... |

## 外部脅威情報（Geminiより）
（本システムに関連するリスクを抽出して記載）

## 要対応事項
（なければ「なし」）

## 推奨事項
...
"""
    write_report('security', call_claude(prompt))


# ─── Team 7: 内部監査 ─────────────────────────────────────────────
def run_internal_audit():
    # 各チームのレポートを読む
    reports = {
        '情報収集': read_report('info_gathering'),
        '分析':     read_report('analysis'),
        'リスク管理': read_report('risk'),
        '投資戦略': read_report('strategy'),
        'セキュリティ': read_report('security'),
        '統括レポート': read_report(f'{TODAY}_daily_report'),
    }

    # 過去の日次レポートを最大5件取得
    past_reports = []
    for p in sorted(REPORT_DIR.glob('*_daily_report.md'), reverse=True):
        if p.stem != f'{TODAY}_daily_report':
            past_reports.append(p.read_text(encoding='utf-8')[:500])
        if len(past_reports) >= 5:
            break
    past_str = '\n---\n'.join(past_reports) if past_reports else '（過去レポートなし）'

    # 監査ログを読む（前回の提案フォローアップ用）
    audit_log_path = Path('reports') / 'audit_log.md'
    prev_audit = audit_log_path.read_text(encoding='utf-8')[-2000:] if audit_log_path.exists() else '（初回）'

    reports_str = '\n\n'.join(f'### {name}\n{content[:1000]}' for name, content in reports.items())

    # ── Step1: Gemini で優れた投資チーム運営のベストプラクティスを調査 ──
    print('  [Gemini] 投資チーム改善情報収集中...')
    g_prompt = f"""プロの投資チーム（ヘッジファンド・資産運用会社）の運営ベストプラクティスについて調査してください。

1. 優れた株式分析レポートの構成要素・品質基準
2. ミネルヴィニ流成長株投資における最新の手法・改善点
3. AIを活用した投資分析の最新事例・ベストプラクティス
4. 個人投資家がプロに近づくための情報収集・分析手法
5. 投資チームの意思決定プロセス改善事例

本日 {TODAY} の情報を含めてください。
"""
    gemini_text, sources = call_gemini(g_prompt)
    save_source_log('内部監査チーム', sources, gemini_text)

    kpi_definitions = build_kpi_check_prompt()

    prompt = f"""あなたは投資チームの「内部監査チーム」です。本日 {TODAY} の全チームを監査し、KPI達成状況を評価して改善提案を行ってください。

## 各チームのKPI定義
{kpi_definitions}

## 本日の各チームレポート
{reports_str}

## 過去レポートのサマリー（最大5件）
{past_str}

## 前回の監査ログ（フォローアップ用）
{prev_audit}

## Geminiが収集した投資チームのベストプラクティス
{gemini_text}

## 評価観点（各5段階）
- 網羅性: KPI定義の全項目をカバーしているか
- 具体性: 数値・銘柄コード・根拠が明記されているか
- 有用性: 投資判断に実際に役立つ内容か
- 一貫性: 過去レポートと矛盾がないか
- 連携性: 前チームの情報を適切に引き継いでいるか
- AI活用度: Gemini+Claudeの二重確認が有効に機能しているか

## 出力フォーマット（必ずこの形式で）
# 内部監査チーム レポート
日付: {TODAY}

## エグゼクティブサマリー
（最重要発見を3点以内で）

## KPI達成状況
| チーム | KPI項目 | 目標 | 達成状況 | 評価 |
|--------|---------|------|---------|------|
| 情報収集 | 必須8項目網羅率 | 100% | XX% | ✅/⚠️/❌ |
| 情報収集 | データ誤り件数 | 0件 | X件 | ✅/⚠️/❌ |
| 分析 | 評価銘柄数 | 5銘柄以上 | X銘柄 | ✅/⚠️/❌ |
| 分析 | 判断理由の具体性 | 根拠3つ以上 | X個 | ✅/⚠️/❌ |
| リスク管理 | DD許容上限遵守 | -10%以内 | XX% | ✅/⚠️/❌ |
| リスク管理 | 損切りライン設定率 | 100% | XX% | ✅/⚠️/❌ |
| 投資戦略 | 平均RR比 | 3.0以上 | X.X | ✅/⚠️/❌ |
| 投資戦略 | アクションプランの具体性 | 全項目明記 | ✅/❌ | ✅/⚠️/❌ |
| レポート統括 | 全チーム統合率 | 100% | XX% | ✅/⚠️/❌ |
| レポート統括 | [事実]/[AI分析]ラベル | 100% | XX% | ✅/⚠️/❌ |
| セキュリティ | 重大脆弱性未報告 | 0件 | X件 | ✅/⚠️/❌ |
| 内部監査 | 前回提案フォローアップ | 100% | XX% | ✅/⚠️/❌ |
（本日評価できないKPIは「-」と記載）

## チーム別評価スコア
| チーム | 網羅性 | 具体性 | 有用性 | 一貫性 | 連携性 | AI活用度 | 総合 | 所見 |
|--------|--------|--------|--------|--------|--------|---------|------|------|
| 情報収集 | /5 | /5 | /5 | /5 | /5 | /5 | /5 | ... |
| 分析 | /5 | /5 | /5 | /5 | /5 | /5 | /5 | ... |
| リスク管理 | /5 | /5 | /5 | /5 | /5 | /5 | /5 | ... |
| 投資戦略 | /5 | /5 | /5 | /5 | /5 | /5 | /5 | ... |
| 統括 | /5 | /5 | /5 | /5 | /5 | /5 | /5 | ... |
| セキュリティ | /5 | /5 | /5 | /5 | /5 | /5 | /5 | ... |

## KPIトレンド分析
（繰り返し未達成のKPI・改善傾向）

## 改善提案
### 優先度: 高（KPI未達成に直結）
...
### 優先度: 中（品質向上）
...

## 新チーム・新KPI提案
（不足機能や追加すべきKPIがあれば）

## 前回提案のフォローアップ
...
"""
    result = call_claude(prompt, max_tokens=6000)
    write_report('internal_audit', result)

    # KPIログ: チーム別スコアをJSONで保存（トレンド分析用）
    kpi_scores = {}
    for line in result.split('\n'):
        # "| チーム名 | X | X | X | X | X | X | X |" の行をパース
        parts = [p.strip() for p in line.split('|') if p.strip()]
        if len(parts) >= 8 and parts[0] in ['情報収集', '分析', 'リスク管理', '投資戦略', '統括', 'セキュリティ']:
            try:
                kpi_scores[parts[0]] = {
                    'coverage': parts[1], 'specificity': parts[2],
                    'usefulness': parts[3], 'consistency': parts[4],
                    'linkage': parts[5], 'ai_usage': parts[6], 'total': parts[7]
                }
            except IndexError:
                pass
    save_kpi_log(kpi_scores)

    # 監査ログに追記
    audit_log_path = Path('reports') / 'audit_log.md'
    summary_lines = [l for l in result.split('\n') if l.startswith('- ') or l.startswith('### 優先度')][:10]
    log_entry = f'\n## {TODAY}\n' + '\n'.join(summary_lines) + '\n'
    existing = audit_log_path.read_text(encoding='utf-8') if audit_log_path.exists() else '# 内部監査ログ\n'
    audit_log_path.write_text(existing + log_entry, encoding='utf-8')
    print(f'  -> audit_log.md 更新')


# ─── メイン ──────────────────────────────────────────────────────
TEAMS = {
    'info':     ('情報収集チーム',   run_info_gathering),
    'analysis': ('分析チーム',       run_analysis),
    'risk':     ('リスク管理チーム', run_risk_management),
    'strategy': ('投資戦略チーム',   run_strategy),
    'report':   ('レポート統括',     run_daily_report),
    'security': ('セキュリティチーム', run_security),
    'audit':    ('内部監査チーム',   run_internal_audit),
}

if __name__ == '__main__':
    target = sys.argv[1] if len(sys.argv) > 1 else 'all'

    if target == 'all':
        for key, (name, fn) in TEAMS.items():
            print(f'\n[{name}] 開始...')
            try:
                fn()
                print(f'[{name}] 完了')
            except Exception as e:
                print(f'[{name}] エラー: {e}', file=sys.stderr)
    elif target in TEAMS:
        name, fn = TEAMS[target]
        print(f'[{name}] 開始...')
        fn()
        print(f'[{name}] 完了')
    else:
        print(f'不明なチーム: {target}')
        print(f'使用可能: {list(TEAMS.keys())} または all')
        sys.exit(1)
