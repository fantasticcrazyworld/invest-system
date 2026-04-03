"""
sync_local.py - GitHubから最新データをローカルに同期するスクリプト

タスクスケジューラで毎日19:00に実行。
PC未起動の場合は次回起動時に自動実行（StartWhenAvailable=true）。

処理フロー:
  1. invest-system-github を git pull（コード最新化）
  2. invest-data を git pull（データ・レポート最新化）
  3. データ品質チェック
     - RS null率が高い / ytd_high_date大量欠損 など
  4. 問題検出 → GitHub Actions を自動再トリガー
"""

import subprocess
import sys
import json
import urllib.request
import urllib.error
import os
from pathlib import Path
from datetime import datetime

# Windows環境でUTF-8出力を強制
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")

# ---- 設定 ---------------------------------------------------------------
INVEST_SYSTEM_DIR = Path(r"C:\Users\yohei\Documents\invest-system-github")
INVEST_DATA_DIR   = Path(r"C:\Users\yohei\Documents\invest-data")
INVEST_DATA_REPO  = "https://github.com/yangpinggaoye15-dotcom/invest-data.git"
GITHUB_REPO       = "yangpinggaoye15-dotcom/invest-system"
SCREENING_WORKFLOW = "daily_screening.yml"
TEAMS_WORKFLOW     = "daily_teams.yml"
LOG_FILE          = INVEST_SYSTEM_DIR / "logs" / "sync_local.log"
MAX_LOG_LINES     = 500   # ログが肥大化しないよう制限

# 品質チェック閾値
RS_NULL_THRESHOLD     = 0.5   # PASSした銘柄のRS null率がこれ以上で異常とみなす
YTD_MISSING_THRESHOLD = 0.5   # PASSした銘柄のytd_high_date欠損率がこれ以上で異常
# -------------------------------------------------------------------------


def log(msg: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {msg}"
    print(line, flush=True)
    LOG_FILE.parent.mkdir(exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    # ログローテーション
    try:
        lines = LOG_FILE.read_text(encoding="utf-8").splitlines()
        if len(lines) > MAX_LOG_LINES:
            LOG_FILE.write_text("\n".join(lines[-MAX_LOG_LINES:]) + "\n", encoding="utf-8")
    except Exception:
        pass


def run_git(args: list, cwd: Path) -> bool:
    cmd = ["git"] + args
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd, timeout=120)
    out = (result.stdout + result.stderr).strip()
    if result.returncode != 0:
        log(f"  NG: git {' '.join(args)}")
        if out:
            log(f"  {out[:300]}")
        return False
    log(f"  OK: git {' '.join(args)}")
    if out and out not in ("Already up to date.", ""):
        log(f"  {out[:300]}")
    return True


def sync_repo(label: str, repo_dir: Path, remote_url: str):
    log(f"--- {label} ---")
    if repo_dir.exists() and (repo_dir / ".git").exists():
        run_git(["pull", "--rebase", "--autostash", "origin", "main"], cwd=repo_dir)
    else:
        log(f"  初回clone: {remote_url} -> {repo_dir}")
        result = subprocess.run(
            ["git", "clone", remote_url, str(repo_dir)],
            capture_output=True, text=True, timeout=300
        )
        out = (result.stdout + result.stderr).strip()
        if result.returncode != 0:
            log(f"  NG: clone失敗\n  {out[:300]}")
        else:
            log(f"  OK: clone完了")


def get_github_token() -> str:
    """git credential storeからGitHubトークンを取得"""
    try:
        result = subprocess.run(
            ["git", "credential", "fill"],
            input="protocol=https\nhost=github.com\n\n",
            capture_output=True, text=True, timeout=5,
            cwd=INVEST_SYSTEM_DIR
        )
        for line in result.stdout.splitlines():
            if line.startswith("password="):
                return line[9:].strip()
    except Exception as e:
        log(f"  トークン取得エラー: {e}")
    return ""


def trigger_workflow(token: str, workflow: str, inputs: dict = None) -> bool:
    """GitHub Actions workflow_dispatch を呼び出す"""
    url = f"https://api.github.com/repos/{GITHUB_REPO}/actions/workflows/{workflow}/dispatches"
    body = {"ref": "main"}
    if inputs:
        body["inputs"] = inputs
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Authorization", f"token {token}")
    req.add_header("Accept", "application/vnd.github.v3+json")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status == 204
    except urllib.error.HTTPError as e:
        log(f"  HTTPエラー {e.code}: {e.read()[:200]}")
        return False
    except Exception as e:
        log(f"  トリガーエラー: {e}")
        return False


def check_data_quality() -> list:
    """
    invest-data の品質チェック。
    返値: 問題リスト（空なら正常）
    各要素は {'issue': str, 'severity': 'error'|'warn', 'fix': str}
    """
    issues = []
    results_path = INVEST_DATA_DIR / "screen_full_results.json"

    if not results_path.exists():
        issues.append({
            "issue": "screen_full_results.json が存在しない",
            "severity": "error",
            "fix": "screening"
        })
        return issues

    try:
        with open(results_path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        issues.append({
            "issue": f"screen_full_results.json 読み込み失敗: {e}",
            "severity": "error",
            "fix": "screening"
        })
        return issues

    stocks = {k: v for k, v in data.items()
              if k != "__meta__" and isinstance(v, dict) and not v.get("error")}
    passed = [v for v in stocks.values() if v.get("passed")]

    if not passed:
        issues.append({
            "issue": "PASSした銘柄が0件",
            "severity": "error",
            "fix": "screening"
        })
        return issues

    # RS26w null チェック
    rs_null = sum(1 for v in passed if v.get("rs26w") is None)
    rs_null_rate = rs_null / len(passed)
    if rs_null_rate >= RS_NULL_THRESHOLD:
        issues.append({
            "issue": f"RS26w null: {rs_null}/{len(passed)}件 ({rs_null_rate:.0%}) — ベンチマーク取得エラーの可能性",
            "severity": "error",
            "fix": "screening"
        })

    # ytd_high_date 欠損チェック
    ytd_missing = sum(1 for v in passed if not v.get("ytd_high_date"))
    ytd_missing_rate = ytd_missing / len(passed)
    if ytd_missing_rate >= YTD_MISSING_THRESHOLD:
        issues.append({
            "issue": f"ytd_high_date 欠損: {ytd_missing}/{len(passed)}件 ({ytd_missing_rate:.0%})",
            "severity": "error",
            "fix": "screening"
        })

    # データ鮮度チェック（メタの更新日時）
    meta = data.get("__meta__", {})
    finished_at = meta.get("finished_at", "")
    if finished_at:
        try:
            finished = datetime.fromisoformat(finished_at)
            age_hours = (datetime.now() - finished).total_seconds() / 3600
            if age_hours > 30:  # 30時間以上古い
                issues.append({
                    "issue": f"データが古い: 最終更新 {finished_at[:16]} ({age_hours:.0f}時間前)",
                    "severity": "warn",
                    "fix": "screening"
                })
        except Exception:
            pass

    # レポートチェック（latest_report.md）
    report_path = INVEST_DATA_DIR / "reports" / "latest_report.md"
    if report_path.exists():
        try:
            mtime = datetime.fromtimestamp(report_path.stat().st_mtime)
            age_hours = (datetime.now() - mtime).total_seconds() / 3600
            if age_hours > 30:
                issues.append({
                    "issue": f"レポートが古い: latest_report.md 最終更新 {age_hours:.0f}時間前",
                    "severity": "warn",
                    "fix": "teams"
                })
        except Exception:
            pass

    return issues


def auto_fix(issues: list):
    """
    問題を自動修正。
    errorレベルの修正が必要なworkflow をトリガーする。
    """
    needs_screening = any(i["severity"] == "error" and i["fix"] == "screening" for i in issues)
    needs_teams     = any(i["severity"] == "error" and i["fix"] == "teams" for i in issues)

    if not (needs_screening or needs_teams):
        log("  警告のみ — GitHub Actions の再トリガーは不要")
        return

    token = get_github_token()
    if not token:
        log("  WARNING: GitHubトークンを取得できませんでした。手動でActions実行してください。")
        log("  手動実行: https://github.com/yangpinggaoye15-dotcom/invest-system/actions")
        return

    if needs_screening:
        log("  daily_screening.yml を再トリガー中...")
        if trigger_workflow(token, SCREENING_WORKFLOW, {"fresh": "false"}):
            log("  OK: スクリーニングワークフロー起動（完了まで約10分）")
            log("  次回sync時に修正されたデータが取得されます")
        else:
            log("  NG: トリガー失敗。手動実行: Actions → Daily Stock Screening → Run workflow")

    if needs_teams:
        log("  daily_teams.yml を再トリガー中...")
        if trigger_workflow(token, TEAMS_WORKFLOW):
            log("  OK: チームレポートワークフロー起動（完了まで約15分）")
        else:
            log("  NG: トリガー失敗。手動実行: Actions → Daily Investment Teams → Run workflow")


def validate_and_fix():
    """同期後にデータ品質をチェックし、問題があれば自動修正（GitHub Actions再トリガー）"""
    log("--- データ品質チェック ---")
    issues = check_data_quality()

    if not issues:
        results_path = INVEST_DATA_DIR / "screen_full_results.json"
        if results_path.exists():
            with open(results_path, encoding="utf-8") as f:
                data = json.load(f)
            passed_count = sum(1 for k, v in data.items()
                               if k != "__meta__" and isinstance(v, dict)
                               and not v.get("error") and v.get("passed"))
            log(f"  品質OK: PASS銘柄 {passed_count}件 — 問題なし")
        else:
            log("  品質OK")
        return

    # 問題を報告
    for issue in issues:
        severity = "ERROR" if issue["severity"] == "error" else "WARN"
        log(f"  [{severity}] {issue['issue']}")

    # 自動修正
    log("  自動修正を開始します...")
    auto_fix(issues)


def main():
    log("=" * 50)
    log("sync_local.py 開始")

    # 1. invest-system-github（コードリポジトリ）
    sync_repo(
        "invest-system-github（コード）",
        INVEST_SYSTEM_DIR,
        "https://github.com/yangpinggaoye15-dotcom/invest-system.git"
    )

    # 2. invest-data（スクリーニング結果・レポート）
    sync_repo(
        "invest-data（データ・レポート）",
        INVEST_DATA_DIR,
        INVEST_DATA_REPO
    )

    # 3. データ品質チェック → 問題があればGitHub Actions再トリガー
    validate_and_fix()

    log("sync_local.py 完了")
    log("=" * 50)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"FATAL ERROR: {e}")
        sys.exit(1)
