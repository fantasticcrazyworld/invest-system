"""チーム共通の runtime context: 日付・曜日モード・ディレクトリ・API クライアント。

env 変数に依存するため、インポート時に ANTHROPIC_API_KEY が必要。
ANTHROPIC_API_KEY が未設定の場合は KeyError で失敗する（本番運用では必須）。
"""
from __future__ import annotations

import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

import anthropic


# ─── 日付・曜日モード ──────────────────────────────────────────
JST = timezone(timedelta(hours=9))
NOW_JST = datetime.now(JST)
TODAY = NOW_JST.strftime('%Y-%m-%d')
WEEKDAY = NOW_JST.weekday()  # 0=月 … 4=金, 5=土, 6=日
IS_MARKET_DAY = WEEKDAY < 5

# 曜日別モード: 各チームのプロンプトで参照する
if WEEKDAY < 5:
    DAY_MODE = 'weekday'
    DAY_LABEL = f'平日（市場稼働日: {TODAY}）'
    DAY_FOCUS = '本日の市場データ取得・銘柄分析・アクションプラン策定'
elif WEEKDAY == 5:
    DAY_MODE = 'saturday'
    DAY_LABEL = f'土曜日（週次振り返り: {TODAY}）'
    DAY_FOCUS = '今週の業績振り返り・KPI評価・分析精度の改善点整理'
else:
    DAY_MODE = 'sunday'
    DAY_LABEL = f'日曜日（翌週準備: {TODAY}）'
    DAY_FOCUS = '翌週の戦略立案・注目銘柄の事前分析・リスクシナリオ整理'


# ─── ディレクトリ ──────────────────────────────────────────────
DATA_DIR = Path(os.environ.get('INVEST_DATA_DIR', 'invest-data'))
REPORT_DIR = Path('reports') / 'daily'
REPORT_DIR.mkdir(parents=True, exist_ok=True)


# ─── API クライアント ───────────────────────────────────────────
client = anthropic.Anthropic(api_key=os.environ['ANTHROPIC_API_KEY'])
MODEL = 'claude-sonnet-4-6'
GEMINI_KEY = os.environ.get('GEMINI_API', '')
GEMINI_URL = 'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent'
