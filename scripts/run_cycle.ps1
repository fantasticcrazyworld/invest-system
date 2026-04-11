# run_cycle.ps1
# 毎日 18:00 にタスクスケジューラから呼び出される
# エージェントチームレポートを実行して invest-data に push する
#
# 変更履歴:
#   2026-04-07: 初版作成
#   2026-04-12: スクリーニング分岐を削除、チームレポートのみに簡略化

$ErrorActionPreference = "Continue"
$BASE = "C:\Users\yohei\Documents\invest-system-github"
$LOG  = "$BASE\logs\cycle_$(Get-Date -Format 'yyyyMMdd_HHmm').log"

New-Item -ItemType Directory -Force -Path "$BASE\logs" | Out-Null

function Log($msg) {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$ts  $msg" | Tee-Object -FilePath $LOG -Append
}

Log "=== エージェントチーム実行開始 ==="

& powershell.exe -NonInteractive -ExecutionPolicy Bypass `
    -File "$BASE\scripts\run_daily_teams.ps1" 2>&1 | Tee-Object -FilePath $LOG -Append

Log "=== エージェントチーム実行完了 ==="
