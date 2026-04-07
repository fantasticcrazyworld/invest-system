# setup_power.ps1
# PCスリープ無効化・高パフォーマンスモード設定
# 【初回のみ実行】

Write-Host "=== 電源設定（スリープ無効化）==="

# スリープ無効（AC電源接続時）
powercfg /change standby-timeout-ac 0
powercfg /change hibernate-timeout-ac 0
powercfg /change monitor-timeout-ac 0

# 高パフォーマンスプランをアクティブに
$hp = powercfg /list | Select-String "高パフォーマンス|High performance" | Select-Object -First 1
if ($hp) {
    $guid = ($hp -split "\s+")[3]
    powercfg /setactive $guid
    Write-Host "✓ 高パフォーマンスプラン有効化: $guid"
} else {
    powercfg /setactive SCHEME_MIN
    Write-Host "✓ 最大パフォーマンスプラン有効化"
}

# 現在の設定確認
Write-Host ""
Write-Host "=== 現在の電源設定 ==="
powercfg /query SCHEME_CURRENT SUB_SLEEP STANDBYIDLE | Select-String "現在|Current"

Write-Host ""
Write-Host "✓ 完了: PCはスリープしなくなります"
Write-Host "  ※ BIOS設定で『AC復帰後に電源ON』を有効にするとさらに安全です"
