# setup_scheduler.ps1
# Windowsタスクスケジューラに投資システムの自動実行タスクを登録する
# 【初回のみ実行】管理者権限不要（ユーザーレベルのタスク）

$BASE = "C:\Users\yohei\Documents\invest-system-github"

# ── タスク1: 日次スクリーニング (平日 15:05 JST) ──────────────────
$action1 = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NonInteractive -ExecutionPolicy Bypass -File `"$BASE\scripts\run_daily_screening.ps1`"" `
    -WorkingDirectory $BASE

# 月〜金 15:05
$trigger1 = New-ScheduledTaskTrigger `
    -Weekly `
    -DaysOfWeek Monday, Tuesday, Wednesday, Thursday, Friday `
    -At "15:05"

$settings1 = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2)

Register-ScheduledTask `
    -TaskName "InvestSystem_DailyScreening" `
    -TaskPath "\InvestSystem\" `
    -Action $action1 `
    -Trigger $trigger1 `
    -Settings $settings1 `
    -Description "ミネルヴィニ全銘柄スクリーニング → invest-data push" `
    -Force

Write-Host "✓ タスク登録: InvestSystem_DailyScreening (平日 15:05)"

# ── タスク2: 8チームレポート (毎日 16:35 JST) ──────────────────────
$action2 = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NonInteractive -ExecutionPolicy Bypass -File `"$BASE\scripts\run_daily_teams.ps1`"" `
    -WorkingDirectory $BASE

# 毎日 16:35
$trigger2 = New-ScheduledTaskTrigger -Daily -At "16:35"

$settings2 = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 3)

Register-ScheduledTask `
    -TaskName "InvestSystem_DailyTeams" `
    -TaskPath "\InvestSystem\" `
    -Action $action2 `
    -Trigger $trigger2 `
    -Settings $settings2 `
    -Description "8チームAIレポート生成 → invest-data push" `
    -Force

Write-Host "✓ タスク登録: InvestSystem_DailyTeams (毎日 16:35)"

Write-Host ""
Write-Host "=== 登録済みタスク一覧 ==="
Get-ScheduledTask -TaskPath "\InvestSystem\" | Select-Object TaskName, State
