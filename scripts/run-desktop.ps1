$ErrorActionPreference = 'Stop'

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot '..')
$desktopDir = Join-Path $repoRoot 'desktop'

if (-not (Test-Path $desktopDir)) {
    throw "Desktop folder not found: $desktopDir"
}

Set-Location $desktopDir

if (-not (Test-Path (Join-Path $desktopDir 'node_modules'))) {
    Write-Host 'Installing desktop dependencies (first run)...'
    npm install
}

Write-Host 'Starting InferenceChain desktop app...'
npm start
