# One-command local setup: create .env if missing, set session secret, start Compose.
$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

$envFile = Join-Path $ProjectRoot ".env"
$exampleFile = Join-Path $ProjectRoot ".env.example"

function New-SessionSecret {
    $bytes = New-Object byte[] 32
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    return [Convert]::ToBase64String($bytes).TrimEnd("=").Replace("+", "x").Replace("/", "y")
}

if (-not (Test-Path $envFile)) {
    if (-not (Test-Path $exampleFile)) {
        throw "Missing .env.example in $ProjectRoot"
    }
    Copy-Item $exampleFile $envFile
    Write-Host "Created .env from .env.example"
}

$content = Get-Content $envFile -Raw
if ($content -match '(?m)^SESSION_SECRET_KEY=(change-me[^\r\n]*)$') {
    $secret = New-SessionSecret
    $content = $content -replace '(?m)^SESSION_SECRET_KEY=.*$', "SESSION_SECRET_KEY=$secret"
    Set-Content -Path $envFile -Value $content.TrimEnd() -NoNewline
    Add-Content -Path $envFile -Value ""
    Write-Host "Generated SESSION_SECRET_KEY in .env"
}

Write-Host "Starting Docker Compose (postgres, redis, api, worker) ..."
docker compose up --build
