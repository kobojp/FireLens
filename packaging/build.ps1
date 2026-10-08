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
Invoke-NativeChecked 'uv.exe' @('run', '--locked', 'ruff', 'format', '--check', '.')
Invoke-NativeChecked 'uv.exe' @('run', '--locked', 'ruff', 'check', '.')
Invoke-NativeChecked 'uv.exe' @('run', '--locked', 'pytest', '-q')
Invoke-NativeChecked 'uv.exe' @('run', '--locked', 'python', 'packaging/generate_icon.py')
Invoke-NativeChecked 'uv.exe' @('run', '--locked', 'pyinstaller', '--clean', '--noconfirm', 'packaging/firelens.spec')
$Exe = Join-Path $Root 'dist\FireLens.exe'
if (-not (Test-Path $Exe)) { throw 'PyInstaller 未產生 FireLens.exe' }
& $Exe --self-test
if ($LASTEXITCODE -ne 0) { throw "打包後 self-test 失敗：$LASTEXITCODE" }
Get-FileHash $Exe -Algorithm SHA256 | Format-List
Write-Host "Build OK: $Exe"
