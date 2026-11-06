$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
if ($env:OS -ne 'Windows_NT') { throw 'FireLens 正式 EXE 必須在 Windows x64 上建置。' }

function Invoke-NativeChecked {
  param(
    [Parameter(Mandatory = $true)][string]$Command,
    [string[]]$Arguments = @()
  )
  & $Command @Arguments
  if ($LASTEXITCODE -ne 0) {
    throw "$Command 執行失敗，exit code: $LASTEXITCODE"
  }
}

Push-Location frontend
try {
  Invoke-NativeChecked 'npm.cmd' @('ci')
  Invoke-NativeChecked 'npm.cmd' @('run', 'lint')
  Invoke-NativeChecked 'npm.cmd' @('run', 'test', '--', '--run')
  Invoke-NativeChecked 'npm.cmd' @('run', 'build')
}
finally {
  Pop-Location
}
Invoke-NativeChecked 'uv.exe' @('sync', '--locked', '--all-groups')
Invoke-NativeChecked 'uv.exe' @('run', '--locked', 'python', 'packaging/check_version_consistency.py')
Invoke-NativeChecked 'uv.exe' @('run', '--locked', 'ruff', 'format', '--check', '.')
Invoke-NativeChecked 'uv.exe' @('run', '--locked', 'ruff', 'check', '.')
Invoke-NativeChecked 'uv.exe' @('run', '--locked', 'pytest', '-q')
Invoke-NativeChecked 'uv.exe' @('run', '--locked', 'python', 'packaging/generate_icon.py')
Invoke-NativeChecked 'uv.exe' @('run', '--locked', 'pyinstaller', '--clean', '--noconfirm', 'packaging/updater.spec')
$UpdaterExe = Join-Path $Root 'dist\FireLensUpdater.exe'
if (-not (Test-Path $UpdaterExe)) { throw 'PyInstaller 未產生 FireLensUpdater.exe' }
$UpdaterHash = (Get-FileHash $UpdaterExe -Algorithm SHA256).Hash.ToLowerInvariant()
$GeneratedDir = Join-Path $Root 'packaging\generated'
New-Item -ItemType Directory -Force -Path $GeneratedDir | Out-Null
Set-Content -LiteralPath (Join-Path $GeneratedDir 'updater.sha256') -Value $UpdaterHash -Encoding ascii
Invoke-NativeChecked 'uv.exe' @('run', '--locked', 'pyinstaller', '--clean', '--noconfirm', 'packaging/firelens.spec')
$Exe = Join-Path $Root 'dist\FireLens.exe'
if (-not (Test-Path $Exe)) { throw 'PyInstaller 未產生 FireLens.exe' }
$SelfTestDir = Join-Path ([System.IO.Path]::GetTempPath()) ("FireLens-build-selftest-" + [guid]::NewGuid().ToString('N'))
$HadDataDir = Test-Path Env:FIRELENS_DATA_DIR
$PreviousDataDir = $env:FIRELENS_DATA_DIR
try {
  New-Item -ItemType Directory -Force -Path $SelfTestDir | Out-Null
  $env:FIRELENS_DATA_DIR = $SelfTestDir
  $SelfTestProcess = Start-Process -FilePath $Exe -ArgumentList '--self-test' -Wait -PassThru
  if ($SelfTestProcess.ExitCode -ne 0) { throw "打包後 self-test 失敗：$($SelfTestProcess.ExitCode)" }
}
finally {
  if ($HadDataDir) { $env:FIRELENS_DATA_DIR = $PreviousDataDir }
  else { Remove-Item Env:FIRELENS_DATA_DIR -ErrorAction SilentlyContinue }
  Remove-Item -LiteralPath $SelfTestDir -Recurse -Force -ErrorAction SilentlyContinue
}
Get-FileHash $Exe -Algorithm SHA256 | Format-List
& (Join-Path $PSScriptRoot 'build-installer.ps1') -SourceExe $Exe -SourceUpdater $UpdaterExe
if ($LASTEXITCODE -ne 0) { throw "安裝精靈建置失敗：$LASTEXITCODE" }
$VersionText = Get-Content (Join-Path $Root 'desktop\version.py') -Raw
if ($VersionText -notmatch '__version__\s*=\s*"([^"]+)"') { throw '無法讀取 FireLens 版本。' }
$Setup = Join-Path $Root "dist\installer\FireLens-$($Matches[1])-setup.exe"
Invoke-NativeChecked 'uv.exe' @('run', '--locked', 'python', 'packaging/update_e2e.py', '--exe', $Exe, '--setup', $Setup)
Write-Host "Build OK: $Exe"
