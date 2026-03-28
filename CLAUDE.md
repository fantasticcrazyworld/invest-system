# CLAUDE.md - invest-system プロジェクト

## プロジェクト概要
ミネルヴィニ流成長株投資のスクリーニング・分析・自動レポートシステム。

**投資目標（3年ロードマップ）**
| フェーズ | 期間 | 資産目標 | 月次リターン |
|---------|------|---------|------------|
| Phase 1 | 〜2026Q2 | 200万→300万 | +33万円/月 |
| Phase 2 | 〜2026Q4 | 300万→600万 | +75万円/月 |
| Phase 3 | 〜2027Q2 | 600万→1,200万 | +150万円/月 |
| 2年目   | 〜2027末 | 1,200万→2,000万 | — |
| 3年目   | 〜2028末 | 2,000万→1億円  | — |

フェーズ移行条件: 勝率50%以上・PF2.0以上・DD10%以内を**2ヶ月連続**で達成

## サイトURL
https://invest-system-six.vercel.app/

---

## アーキテクチャ全体図

```
[J-Quants API]  →  run_screen_full.py  →  screen_full_results.json
                   stock_mcp_server.py  →  chart/fins/pattern/timeline_data.json
                                  ↓
        [GitHub Actions 15:05 JST] daily_screening.yml
                                  ↓
              invest-data repo (public / yangpinggaoye15-dotcom)
                                  ↓
              index.html (Vercel)  ←  raw.githubusercontent.com

[GitHub Actions after screening] daily_teams.yml
  └── run_teams.py (7チーム)
        ├── Gemini API (Google Search grounding) — リアルタイム情報収集
        ├── Claude API (claude-sonnet-4-6) — 構造化分析
        └── reports/daily/*.md → invest-data/reports/
```

---

## ファイル構成

### コアファイル
| ファイル | 役割 |
|---------|------|
| `index.html` | サイト全体（HTML+CSS+JS一体、~4000行） |
| `stock_mcp_server.py` | MCPサーバー（Claude Desktop用、40+ツール） |
| `run_screen_full.py` | 自動スクリーニング（GitHub Actions + ローカル） |
| `run_teams.py` | 7チーム投資チーム自動実行スクリプト |

### API（Vercel Serverless Functions）
| ファイル | 役割 |
|---------|------|
| `api/claude.js` | Claude APIプロキシ（`ANTHROPIC_API_KEY`環境変数） |
| `api/gemini.js` | Gemini APIプロキシ（`GEMINI_API`環境変数） |

### ワークフロー
| ファイル | スケジュール | 役割 |
|---------|------------|------|
| `.github/workflows/daily_screening.yml` | 毎平日 15:05 JST | スクリーニング → invest-data sync |
| `.github/workflows/daily_teams.yml` | screening完了後 | 7チームレポート生成 |

### レポート（`reports/daily/`）
| ファイル | チーム |
|---------|------|
| `info_gathering.md` | 情報収集チーム |
| `analysis.md` | 分析チーム |
| `risk.md` | リスク管理チーム |
| `strategy.md` | 投資戦略チーム |
| `internal_audit.md` | 内部監査チーム |
| `security.md` | セキュリティチーム |
| `verification.md` | 検証チーム |
| `YYYY-MM-DD_daily_report.md` | レポート統括 |
| `latest_report.md` | 最新版（サイト表示用） |
| `source_log.md` | 情報源・信頼度ログ（レポートには非掲載） |
| `simulation_log.json` | シミュレーション追跡ログ |
| `simulation_daily.md` | シミュレーション日次レポート |

### 生成JSONファイル（ルート）
| ファイル | 生成元 |
|---------|------|
| `chart_data.json` | `stock_mcp_server.py export_chart_data()` |
| `fins_data.json` | `stock_mcp_server.py export_fins_data()` |
| `pattern_data.json` | `stock_mcp_server.py export_pattern_data()` |
| `timeline_data.json` | `stock_mcp_server.py export_timeline_data()` |

---

## 投資チーム構成

### 組織図
```
オーナー（最終意思決定）
  └── 統括マネージャー（意思決定以外すべて）
        ├── 情報収集チーム（米国市場担当 / 日本市場担当 / マクロ地政学担当）
        ├── 分析チーム（テクニカル担当 / ファンダメンタル担当 / パターン検出担当）
        ├── リスク管理チーム（ポジション管理担当 / 市場リスク担当 / DD管理担当）
        ├── 投資戦略チーム（市場フェーズ判定担当 / エントリー設計担当 / エグジット戦略担当）
        ├── レポート統括（日次統合レポート）
        ├── 検証チーム（シミュレーション追跡担当 / 差異分析担当 / KPIフィードバック担当）
        ├── セキュリティチーム（コード監査 / 脅威情報収集）
        └── 内部監査チーム（全チーム品質評価 / 改善提案）
```

### 情報伝達フロー
```
情報収集 → 分析 → リスク管理 → 投資戦略 → レポート統括
  ↑                                              ↓
  └─────────────── 検証チームフィードバック ←────┘
                   内部監査 → 全チームへ
```

### 各チームのAPI利用
- **Gemini** (Google Search grounding): リアルタイム市場情報・ニュース収集
- **Claude** (claude-sonnet-4-6): 構造化分析・判断・レポート生成
- すべてのレポートは `[事実]` / `[AI分析]` ラベルで明示

---

## KPI（Phase 1 基準 / 運用資産200万円）

### チーム全体
| KPI | 目標 | 具体額 |
|-----|------|-------|
| 月次損益 | +16.7% | +33万円/月 |
| 勝率 | 50%以上 | 2回に1回利確 |
| プロフィットファクター | 2.0以上 | — |
| 最大ドローダウン | -10%以内 | -20万円が上限 |
| 平均RR比 | 3.0以上 | 利益+9万 vs 損失-3万 |

### 詳細KPI → `reports/goals_kpi.md` 参照

---

## シミュレーションシステム
- **対象**: Aランク銘柄から最も買いに近い1銘柄を毎日自動選定
- **追跡期間**: 2週間（10営業日）
- **終了条件**: 損切り到達 / 目標①到達 / 2週間経過 のいずれか早い方
- **記録**: `simulation_log.json`（差異・原因・学習パターン蓄積）
- **実行**: SessionStartフック or daily_teams.yml で自動更新

---

## データフロー詳細
1. `run_screen_full.py --fresh` → 全銘柄スクリーニング → `data/screen_full_results.json`
2. `stock_mcp_server.py` の export 関数群 → `chart_data.json` 等（ルートに生成）
3. `daily_screening.yml` → invest-data リポジトリに sync
4. `daily_teams.yml` → Gemini+Claude で7チームレポート → invest-data/reports/ に sync
5. `index.html` → `raw.githubusercontent.com` から JSON・MD を fetch して表示

---

## パス設定
- **ローカル**: `C:\Users\yohei\Documents\invest-system`（デフォルト）
- **GitHub Actions**: 環境変数 `INVEST_BASE_DIR` / `INVEST_GITHUB_DIR` / `INVEST_DATA_DIR` で上書き
- **絶対にパスを直書きしない** → 必ず `os.environ.get()` でフォールバック

---

## API・認証

### GitHub Secrets（GitHub Actions用）
| Secret | 用途 |
|--------|------|
| `ANTHROPIC_API_KEY` | Claude API |
| `GEMINI_API` | Gemini API (Google Search grounding含む) |
| `JQUANTS_API_KEY` | J-Quants V2 株価・業績データ |
| `DATA_REPO_TOKEN` | invest-data リポジトリへのpush権限 |

### Vercel環境変数（サイトAPI proxy用）
| 変数 | 用途 |
|------|------|
| `ANTHROPIC_API_KEY` | `/api/claude` proxy |
| `GEMINI_API` | `/api/gemini` proxy |

### localStorage（サイト内ユーザーデータ）
| キー | 内容 |
|------|------|
| `memo_{code}` | 銘柄メモ |
| `sim_{code}` | シミュレーション設定 |
| `knowledge_{code}` | ナレッジバッファ |
| `wl_local` | 監視銘柄（サイトから追加分） |
| `pf_local` | ポートフォリオ（サイトから追加分） |
| `pf_cash` | 資金残高 |
| `pf_history` | 売却履歴 |
| `cf_presets` | カスタムフィルタプリセット |
| `ai_hist_{code}` | AI分析履歴 |

---

## やってはいけないこと

1. **JSONにNaN/Inf値を出力しない** → `_sanitize_nans()` を必ず通す
2. **invest-dataリポジトリをPrivateにしない** → サイトのデータ読み込みが全停止
3. **CDNスクリプトを追加しない** → セキュリティリスク。ライブラリはローカルファイルとして配置
4. **Windowsパスを直書きしない** → GitHub Actions（Ubuntu）で動かなくなる
5. **APIキーをlocalStorageに保存しない** → Vercel環境変数 + `/api/` proxyを使う
6. **Gemini APIキーをHTTPヘッダーで送らない** → CORSプリフライトで失敗
7. **レポートに事実とAI分析を混在させない** → `[事実]` / `[AI分析]` ラベルを必ず付ける
8. **投資判断を自動実行しない** → シミュレーションのみ。最終意思決定はオーナー

---

## export対象銘柄のロジック
chart/fins/pattern/timeline データの対象:
- 監視銘柄（watchlist.json）→ 常に含む
- ポートフォリオ（portfolio.json）→ 常に含む
- 年初来高値更新圏（price >= ytd_high × 0.98）→ 自動選定
- extra_codes引数 → 手動追加

---

## テスト方法
```bash
# ローカルでexport関数テスト
python -c "import stock_mcp_server as s; print(s.export_chart_data())"

# GitHub Actions手動実行
Actions → Daily Stock Screening → Run workflow
Actions → Daily Investment Teams → Run workflow

# サイト確認
https://invest-system-six.vercel.app/ を Ctrl+Shift+R で強制リロード
```
