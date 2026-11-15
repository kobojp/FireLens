param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^v\d+\.\d+\.\d+$')]
    [string]$Tag,
    [string]$AssetsDirectory = 'release'
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Push-Location $Root
try {
    $result = & uv run --locked python packaging/check_release_readiness.py --tag $Tag --assets-dir $AssetsDirectory --json
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    $checked = ($result -join "`n") | ConvertFrom-Json
    $arguments = @('release', 'create', $Tag) + @($checked.assets) + @(
        '--title', "FireLens $Tag", '--notes-file', $checked.notes, '--verify-tag'
    )
    & gh @arguments
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
finally { Pop-Location }
