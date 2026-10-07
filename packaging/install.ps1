param(
  [string]$SourceExe = (Join-Path (Split-Path -Parent $PSScriptRoot) 'dist\FireLens.exe')
)
$ErrorActionPreference = 'Stop'
if ($env:OS -ne 'Windows_NT') { throw '安裝腳本僅支援 Windows。' }
if (-not (Test-Path $SourceExe)) { throw "找不到 FireLens.exe：$SourceExe" }
$InstallDir = Join-Path $env:LOCALAPPDATA 'Programs\FireLens'
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
$Target = Join-Path $InstallDir 'FireLens.exe'
Copy-Item -Force $SourceExe $Target
$Shell = New-Object -ComObject WScript.Shell
$ShortcutPath = Join-Path ([Environment]::GetFolderPath('StartMenu')) 'Programs\FireLens.lnk'
$Shortcut = $Shell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = $Target
$Shortcut.WorkingDirectory = $InstallDir
$Shortcut.Save()
Write-Host "Installed: $Target"
