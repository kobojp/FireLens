param(
  [string]$SourceExe = (Join-Path (Split-Path -Parent $PSScriptRoot) 'dist\FireLens.exe'),
  [string]$OutputDir = (Join-Path (Split-Path -Parent $PSScriptRoot) 'dist\installer')
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
if ($env:OS -ne 'Windows_NT') { throw 'FireLens 安裝精靈只能在 Windows 上建置。' }
if (-not (Test-Path -LiteralPath $SourceExe)) { throw "找不到 FireLens.exe：$SourceExe" }

$VersionText = Get-Content (Join-Path $Root 'desktop\version.py') -Raw
if ($VersionText -notmatch '__version__\s*=\s*"([^"]+)"') { throw '無法讀取 FireLens 版本。' }
$Version = $Matches[1]

$Candidates = @(
  $env:INNO_SETUP_COMPILER,
  (Join-Path $env:LOCALAPPDATA 'Programs\Inno Setup 6\ISCC.exe'),
  (Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6\ISCC.exe'),
  (Join-Path $env:ProgramFiles 'Inno Setup 6\ISCC.exe')
) | Where-Object { $_ }

$Command = Get-Command 'ISCC.exe' -ErrorAction SilentlyContinue
if ($Command) { $Candidates = @($Command.Source) + $Candidates }
$Iscc = $Candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $Iscc) {
  throw '找不到 Inno Setup 6 編譯器 ISCC.exe。請先安裝 Inno Setup 6，或設定 INNO_SETUP_COMPILER。'
}

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$Iss = Join-Path $PSScriptRoot 'FireLens.iss'
& $Iscc "/DAppVersion=$Version" "/DSourceExe=$SourceExe" "/O$OutputDir" $Iss
if ($LASTEXITCODE -ne 0) { throw "Inno Setup 編譯失敗，exit code: $LASTEXITCODE" }

$Setup = Join-Path $OutputDir "FireLens-$Version-setup.exe"
if (-not (Test-Path -LiteralPath $Setup)) { throw "安裝精靈未產生：$Setup" }
Get-FileHash $Setup -Algorithm SHA256 | Format-List
Write-Host "Installer OK: $Setup"
