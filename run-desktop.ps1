$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
Push-Location frontend
npm ci
npm run build
Pop-Location
uv sync --locked
uv run --locked python -m desktop.main
