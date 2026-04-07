# run_daily_screening.ps1
# 毎日 15:05 JST に自動実行 — スクリーニング + invest-data に push
# タスクスケジューラから呼び出す

$ErrorActionPreference = "Stop"
$BASE   = "C:\Users\yohei\Documents\invest-system-github"
$DATA   = "C:\Users\yohei\Documents\invest-data"
$PYTHON = "C:\Users\yohei\AppData\Local\Python\bin\python.exe"
$LOG    = "$BASE\logs\screening_$(Get-Date -Format 'yyyyMMdd').log"

New-Item -ItemType Directory -Force -Path "$BASE\logs" | Out-Null

function Log($msg) {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$ts  $msg" | Tee-Object -FilePath $LOG -Append
}

Log "=== 日次スクリーニング開始 ==="

# 1. スクリーニング実行
Log "screen_full 開始..."
Set-Location $BASE
& $PYTHON run_screen_full.py --fresh 2>&1 | Tee-Object -FilePath $LOG -Append
if ($LASTEXITCODE -ne 0) { Log "WARNING: screen_full.py エラー (続行)" }

# 2. screen_full_results.json を invest-data に同期
$src = "$BASE\data\screen_full_results.json"
$dst = "$DATA\screen_full_results.json"
if (Test-Path $src) {
    Copy-Item $src $dst -Force
    Log "screen_full_results.json を invest-data にコピー"
} else {
    Log "WARNING: screen_full_results.json が見つかりません"
}

# 3. invest-data を git push
Log "invest-data を GitHub に push..."
Set-Location $DATA
git add screen_full_results.json
$today = Get-Date -Format "yyyy-MM-dd"
git commit -m "screening $today (local)" --allow-empty
git push origin main 2>&1 | Tee-Object -FilePath $LOG -Append
if ($LASTEXITCODE -ne 0) { Log "WARNING: git push エラー" }

Log "=== スクリーニング完了 ==="
