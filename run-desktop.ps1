param([switch]$NoPause)

$ErrorActionPreference = 'Stop'
$script:LaunchExitCode = 0
$TranscriptStarted = $false
$LaunchLog = $null

function Invoke-LaunchCommand {
    param([string]$Command, [string[]]$Arguments)
    $previousPreference = $ErrorActionPreference
    try {
        # Windows PowerShell otherwise treats native stderr warnings as errors.
        $ErrorActionPreference = 'Continue'
        & $Command @Arguments
        $nativeExit = $LASTEXITCODE
    }
    finally { $ErrorActionPreference = $previousPreference }
    if ($nativeExit -ne 0) {
        $script:LaunchExitCode = $nativeExit
        throw "$Command $($Arguments -join ' ') 執行失敗（退出碼 $nativeExit）。"
    }
}

Push-Location $PSScriptRoot
try {
    $dataDirectory = if ($env:FIRELENS_DATA_DIR) { $env:FIRELENS_DATA_DIR }
        else { Join-Path $env:LOCALAPPDATA 'FireLens' }
    $logDirectory = Join-Path $dataDirectory 'logs'
    New-Item -ItemType Directory -Force -Path $logDirectory | Out-Null
    $LaunchLog = Join-Path $logDirectory ("desktop-launch-{0}-{1}.log" -f (Get-Date -Format 'yyyyMMdd-HHmmss'), $PID)
    Start-Transcript -LiteralPath $LaunchLog | Out-Null
    $TranscriptStarted = $true
    Get-Command npm.cmd, uv -ErrorAction Stop | Out-Null
    Push-Location (Join-Path $PSScriptRoot 'frontend')
    try {
        Invoke-LaunchCommand 'npm.cmd' @('ci')
        Invoke-LaunchCommand 'npm.cmd' @('run', 'build')
    }
    finally { Pop-Location }
    Invoke-LaunchCommand 'uv' @('sync', '--locked')
    Invoke-LaunchCommand 'uv' @('run', '--locked', 'python', '-m', 'desktop.main')
}
catch {
    if ($script:LaunchExitCode -eq 0) { $script:LaunchExitCode = 1 }
    Write-Host "FireLens 啟動失敗： $($_.Exception.Message)" -ForegroundColor Red
    if ($LaunchLog) { Write-Host "啟動紀錄： $LaunchLog" }
    if (-not $NoPause -and [Environment]::UserInteractive -and -not [Console]::IsInputRedirected) {
        Read-Host '請先閱讀以上錯誤，按 Enter 關閉' | Out-Null
    }
}
finally {
    if ($TranscriptStarted) { Stop-Transcript | Out-Null }
    Pop-Location
}
exit $script:LaunchExitCode
