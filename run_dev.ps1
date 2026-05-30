# Mnemosyne Forge dev startup script
# Usage: .\run_dev.ps1

$ErrorActionPreference = "Stop"
Write-Host "=== Mnemosyne Forge / 造枝 ===" -ForegroundColor Cyan

# Check for .env
if (Test-Path ".env") {
    Write-Host "Loading .env..." -ForegroundColor Green
    Get-Content ".env" | ForEach-Object {
        if ($_ -match '^\s*([^#][^=]+)=(.*)$') {
            [Environment]::SetEnvironmentVariable($matches[1], $matches[2], "Process")
        }
    }
} else {
    Write-Host "No .env found - create one with your API keys (see README)" -ForegroundColor Yellow
}

# Install deps if needed
if (-not (Get-Command uvicorn -ErrorAction SilentlyContinue)) {
    Write-Host "Installing dependencies..." -ForegroundColor Green
    py -m pip install -r requirements.txt
}

# Clean old processes
Get-Process -Name "python*","cloudflared*" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 1
Remove-Item -Path "app\__pycache__" -Recurse -Force -ErrorAction SilentlyContinue

# Start server
Write-Host "Starting server on http://127.0.0.1:8010 ..." -ForegroundColor Cyan
Start-Process -FilePath "py" -ArgumentList "-u","-m","uvicorn","app.server:app","--host","127.0.0.1","--port","8010","--reload"
Start-Sleep -Seconds 3

# Start cloudflared tunnel
$cloudflared = "E:\忆界树Project_Mnemosyne\tools\cloudflared.exe"
if (Test-Path $cloudflared) {
    $tunnelLog = Join-Path $PSScriptRoot "tunnel.log"
    Start-Process -FilePath $cloudflared -ArgumentList "tunnel","--url","http://127.0.0.1:8010" -NoNewWindow -RedirectStandardError $tunnelLog
    Start-Sleep -Seconds 6
    $url = Get-Content $tunnelLog | Select-String "trycloudflare.com" | ForEach-Object { $_.Line -replace '.*?(https://[^ ]+).*','$1' } | Select-Object -First 1
    if ($url) {
        Write-Host "" -ForegroundColor Cyan
        Write-Host "  公网地址: $url" -ForegroundColor Green
        Write-Host ""
    }
}

Write-Host "本地地址: http://127.0.0.1:8010" -ForegroundColor Cyan
Write-Host "按 Ctrl+C 后运行 Stop-Process -Name python*,cloudflared* 来停止" -ForegroundColor Yellow

# Keep window open
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
