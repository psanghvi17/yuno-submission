# Quick smoke check after docker compose up.
param(
    [string]$BaseUrl = "http://localhost:3000"
)

$ErrorActionPreference = "Stop"

Write-Host "Checking $BaseUrl/health ..."
$health = Invoke-RestMethod -Uri "$BaseUrl/health" -Method Get
if ($health.status -ne "ok") {
    throw "Health check failed: $($health | ConvertTo-Json -Compress)"
}
Write-Host "OK: health"

Write-Host "Checking login page ..."
$response = Invoke-WebRequest -Uri "$BaseUrl/auth/login" -UseBasicParsing
if ($response.StatusCode -ne 200) {
    throw "Login page returned $($response.StatusCode)"
}
Write-Host "OK: login page"

Write-Host "All checks passed."
