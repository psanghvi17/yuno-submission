# Reset Telegram getUpdates / webhook state for local dev (fixes 409 Conflict).
# Run from repo root:  .\scripts\reset_telegram.ps1

$ProjectRoot = Split-Path $PSScriptRoot -Parent
Set-Location $ProjectRoot

function Get-TelegramToken {
    $line = Get-Content ".env" -ErrorAction SilentlyContinue | Where-Object {
        $_ -match '^\s*TELEGRAM_BOT_TOKEN\s*=\s*(.+)\s*$'
    } | Select-Object -First 1
    if (-not $line) {
        throw "TELEGRAM_BOT_TOKEN not found in .env"
    }
    $token = $Matches[1].Trim().Trim('"').Trim("'") -replace "`r", ""
    if ($token -notmatch '^\d+:[A-Za-z0-9_-]+$') {
        throw "TELEGRAM_BOT_TOKEN looks invalid. Check .env for extra spaces or line-ending issues."
    }
    return $token
}

Write-Host "==> Stopping Docker stack (releases in-container poller)..."
cmd /c "docker compose down 2>&1"

Write-Host "==> Waiting 30s for Telegram to release the getUpdates connection..."
Write-Host "    (long-poll can stay open up to ~20s after the process exits)"
Start-Sleep -Seconds 30

$token = Get-TelegramToken
$base = "https://api.telegram.org/bot$token"

Write-Host "==> deleteWebhook (drop pending updates)..."
try {
    $delete = Invoke-RestMethod -Uri "$base/deleteWebhook?drop_pending_updates=true" -Method Post
    Write-Host ($delete | ConvertTo-Json -Compress)
} catch {
    Write-Host "deleteWebhook failed: $_"
}

Write-Host "==> getWebhookInfo..."
try {
    $info = Invoke-RestMethod -Uri "$base/getWebhookInfo" -Method Get
    Write-Host ($info | ConvertTo-Json -Compress)
} catch {
    Write-Host "getWebhookInfo failed: $_"
}

Write-Host "==> Probing getUpdates (should NOT return 409)..."
try {
    $probe = Invoke-RestMethod -Uri "$base/getUpdates?timeout=0" -Method Get
    if ($probe.ok) {
        Write-Host "OK: getUpdates slot is free (result count: $($probe.result.Count))"
    } else {
        Write-Host ($probe | ConvertTo-Json -Compress)
    }
} catch {
    $status = $_.Exception.Response.StatusCode.value__
    if ($status -eq 409) {
        Write-Host ""
        Write-Host "STILL 409: Another machine or app is using this bot token."
        Write-Host "  - Revoke token in @BotFather (/revoke), paste NEW token in .env"
        Write-Host "  - Check CapRover / another PC / second docker project"
        Write-Host "  - Wait 60s and run this script again"
    } else {
        Write-Host "getUpdates probe failed: $_"
    }
}

Write-Host ""
Write-Host "==> Starting stack..."
cmd /c "docker compose up -d 2>&1"

Write-Host ""
Write-Host "Done. Watch logs:  docker compose logs api -f"
Write-Host "Then message your bot in Telegram (not @userinfobot)."
