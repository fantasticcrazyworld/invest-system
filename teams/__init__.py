"""teams package: 9 チーム構成の Investment Team System。

`run_teams.py` はこのパッケージの `TEAMS` を使って各チームを順次実行する。
外部コードは `from teams import TEAMS, TEAM_REPORT_MAP` で利用可能。
"""
from teams.info import run_info_gathering
from teams.analysis import run_analysis
from teams.risk import run_risk_management
from teams.strategy import run_strategy
from teams.report import run_daily_report
from teams.verification import run_verification
from teams.security import run_security
from teams.audit import run_internal_audit
from teams.hr import run_hr


TEAMS = {
    'info':         ('情報収集チーム',             run_info_gathering),
    'analysis':     ('銘柄選定・仮説チーム',       run_analysis),
    'risk':         ('リスク管理チーム',           run_risk_management),
    'strategy':     ('投資戦略チーム',             run_strategy),
    'report':       ('レポート統括',               run_daily_report),
    'verification': ('シミュレーション追跡・検証チーム', run_verification),
    'security':     ('セキュリティチーム',         run_security),
    'audit':        ('内部監査チーム',             run_internal_audit),
    'hr':           ('人事部',                     run_hr),
}

# チームキー → レポートファイル名のマッピング（shared_context更新用）
TEAM_REPORT_MAP = {
    'info':         'info_gathering',
    'analysis':     'analysis',
    'risk':         'risk',
    'strategy':     'strategy',
    'report':       'latest_report',
    'verification': 'verification',
    'security':     'security',
    'audit':        'internal_audit',
    'hr':           'hr_report',
}
