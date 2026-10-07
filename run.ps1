$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
Push-Location frontend
npm ci
npm run build
Pop-Location
uv sync --locked
uv run --locked uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
