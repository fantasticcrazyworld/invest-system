"""Phase E Pass 2: app.js を機能別モジュールに分割する一度限りのスクリプト.

方針: 関数開始位置を列挙し、各関数は「次の関数開始位置の直前まで」として切り出す。
間にある変数宣言や即時実行コードは直前の関数ブロックに含まれる。
最初の関数の前のコード（DATA_URL 等のグローバル宣言）は common.js の先頭へ。
末尾の初期化コード（loadData() 等）は common.js の末尾へ。
"""
import os
import re

SRC = 'assets/js/app.js'
OUT_DIR = 'assets/js/'

FUNC_MAP = {
    # common
    'gk': 'common', 'sk': 'common',
    'loadData': 'common',
    'showPage': 'common', 'closeDetail': 'common',
    'mdToHtml': 'common',
    'fmtYen': 'common', 'fmtPct': 'common', 'fmtNum': 'common',
    'growthClass': 'common', 'dedupFY': 'common',
    'getMemo': 'common', 'saveMemo': 'common',
    'getKnowledge': 'common', 'saveKnowledge': 'common', 'getKnowledgeContext': 'common',
    'getLocalWL': 'common', 'saveLocalWL': 'common',
    'getLocalPF': 'common', 'saveLocalPF': 'common',
    'loadChartData': 'common', 'loadPatternData': 'common',
    'loadWatchlist': 'common', 'loadPortfolio': 'common',
    'loadFinsData': 'common', 'loadTimeline': 'common',
    'loadKnowledge': 'common', 'loadIndexData': 'common',
    'loadKpiLog': 'common', 'loadSimLog': 'common',
    'analyzeVolume': 'common',
    'codeSector': 'common',
    # screening + detail panel
    'updateLabel': 'screening',
    'toggleRS': 'screening', 'toggleYTD': 'screening', 'toggleVol': 'screening', 'togglePat': 'screening',
    'resetFilters': 'screening',
    'applyFilters': 'screening',
    'renderTable': 'screening',
    'evalCustomFilter': 'screening',
    'savePreset': 'screening', 'renderPresets': 'screening', 'applyPreset': 'screening',
    'showDetail': 'screening',
    'swTab': 'screening',
    'aiLoad': 'screening', 'aiShow': 'screening', 'aiErr': 'screening',
    'runG': 'screening', 'runC': 'screening',
    'saveAIHistory': 'screening', 'loadAIHistory': 'screening',
    'renderAIHistory': 'screening', 'toggleHistory': 'screening',
    # chat
    'toggleChat': 'chat',
    'addChatMsg': 'chat', 'sendSuggestion': 'chat', 'sendChat': 'chat',
    # report
    'initReportPage': 'report',
    'loadReport': 'report', 'selectReportTeam': 'report', 'loadReportWithFallback': 'report',
    'loadDateReport': 'report',
    'renderTeamKpiSection': 'report',
    # simulation
    'initSimPage': 'simulation',
    'normalizeSim': 'simulation',
    'getSimHistory': 'simulation', 'getSimActives': 'simulation',
    'renderSimPage': 'simulation',
    'initSim': 'simulation',
    'runSim': 'simulation', 'aiSim': 'simulation', 'saveSim': 'simulation',
    'runBacktest': 'simulation',
    'initPosCalc': 'simulation', 'calcPositionSize': 'simulation',
    # kpi
    'initKpiPage': 'kpi',
    'renderKpiPage': 'kpi',
    # chart
    'loadChart': 'chart', 'openChart': 'chart',
    'switchTF': 'chart',
    'resampleWeekly': 'chart', 'resampleMonthly': 'chart',
    'renderStockTrend': 'chart',
    # fins
    'loadFins': 'fins', 'openFins': 'fins',
    # watchlist
    'renderWatchlist': 'watchlist',
    'addToWatchlist': 'watchlist', 'removeFromWatchlist': 'watchlist',
    # portfolio
    'renderPortfolio': 'portfolio',
    'addToPortfolio': 'portfolio', 'sellStock': 'portfolio', 'removeFromPortfolio': 'portfolio',
    'saveCash': 'portfolio', 'loadCash': 'portfolio',
    'saveEquitySnapshot': 'portfolio', 'renderEquityCurve': 'portfolio',
    # health
    'saveHealthSnapshot': 'health', 'renderHealthChart': 'health',
    'renderSectorDist': 'health',
    'switchIndex': 'health', 'switchIdxTF': 'health',
    'renderIndexChart': 'health', 'renderIdxPerf': 'health',
    'calcTrend': 'health',
    'renderMarketTrend': 'health',
    'onIdxCompareChange': 'health', 'showIdxCompare': 'health', 'hideIdxCompare': 'health',
}

FILE_ORDER = ['common', 'screening', 'chat', 'chart', 'fins',
              'watchlist', 'portfolio', 'health', 'simulation', 'kpi', 'report', 'init']

FN_PATTERN = re.compile(r'(?:(?<=^)|(?<=\}))(async\s+)?function\s+(\w+)\s*\(', re.MULTILINE)

INIT_MARKER = 'loadData();loadChartData()'


def main():
    src = open(SRC, encoding='utf-8').read()

    # 末尾の初期化コードを分離
    init_idx = src.rfind(INIT_MARKER)
    if init_idx < 0:
        raise SystemExit(f'init marker not found: {INIT_MARKER}')
    body = src[:init_idx].rstrip()
    init_code = '\n' + src[init_idx:].rstrip() + '\n'

    # 関数開始位置を列挙
    matches = list(FN_PATTERN.finditer(body))
    if not matches:
        raise SystemExit('no function definitions found')

    buckets = {name: [] for name in FILE_ORDER}
    unknown = []

    # 最初の関数の前 = prelude (グローバル変数宣言) → common
    if matches[0].start() > 0:
        buckets['common'].append(body[:matches[0].start()])

    for i, m in enumerate(matches):
        name = m.group(2)
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        bucket = FUNC_MAP.get(name)
        if bucket is None:
            unknown.append(name)
            bucket = 'common'
        buckets[bucket].append(body[start:end])

    # 初期化コードは init.js に分離（全関数定義後に実行される必要がある）
    buckets['init'].append(init_code)

    if unknown:
        print('WARNING: unmapped functions (placed in common.js):')
        for n in unknown:
            print('  -', n)

    total_bytes = 0
    for name in FILE_ORDER:
        content = ''.join(buckets[name])
        if content and not content.endswith('\n'):
            content += '\n'
        path = os.path.join(OUT_DIR, name + '.js')
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f'{name}.js: {len(content):>7} bytes')
        total_bytes += len(content)

    print('Total bytes:', total_bytes)
    print('Original bytes:', len(src))
    print('Delta:', total_bytes - len(src), '(should be ~0)')


if __name__ == '__main__':
    main()
