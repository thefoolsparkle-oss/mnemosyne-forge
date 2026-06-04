# Mnemosyne Forge dev startup script
# Usage: .\run_dev.ps1

$ErrorActionPreference = "Stop"
Write-Host "=== Mnemosyne Forge ===" -ForegroundColor Cyan

function Resolve-Python {
    $candidates = @(
        "C:\Users\Yue\AppData\Local\Programs\Python\Python314\python.exe",
        "C:\Users\Yue\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe",
        "python",
        "py"
    )

    foreach ($candidate in $candidates) {
        if ($candidate -like "*.exe") {
            if (Test-Path $candidate) {
                & $candidate -c "import sys; print(sys.executable)" 2>$null 1>$null
                if ($LASTEXITCODE -eq 0) { return $candidate }
            }
            continue
        }
        $cmd = Get-Command $candidate -ErrorAction SilentlyContinue
        if ($cmd) {
            & $cmd.Source -c "import sys; print(sys.executable)" 2>$null 1>$null
            if ($LASTEXITCODE -eq 0) { return $cmd.Source }
        }
    }

    throw "No Python executable found. Please install Python 3.11+ or update run_dev.ps1."
}

$PythonExe = Resolve-Python
Write-Host "Using Python: $PythonExe" -ForegroundColor Green

# Some Windows shells expose both Path and PATH, which can make Start-Process fail.
$pathValue = [Environment]::GetEnvironmentVariable("Path", "Process")
if (-not $pathValue) {
    $pathValue = [Environment]::GetEnvironmentVariable("PATH", "Process")
}
Remove-Item Env:Path -ErrorAction SilentlyContinue
Remove-Item Env:PATH -ErrorAction SilentlyContinue
$env:Path = $pathValue

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
& $PythonExe -c "import fastapi, uvicorn, pydantic, yaml, httpx" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Installing dependencies..." -ForegroundColor Green
    & $PythonExe -m pip install -r requirements.txt
}

# Clean only our own server (by port match)
$oldServer = Get-WmiObject Win32_Process -Filter "CommandLine LIKE '%uvicorn app.server:app%port 8010%'" -ErrorAction SilentlyContinue
if ($oldServer) { $oldServer.Terminate() | Out-Null }
Start-Sleep -Seconds 1
Remove-Item -Path "app\__pycache__" -Recurse -Force -ErrorAction SilentlyContinue

# Start server (no --reload for stability)
$reloadFlag = if ($args -contains "-Reload") { @("--reload") } else { @() }
Write-Host "Starting server on http://127.0.0.1:8010 ..." -ForegroundColor Cyan
$proc = Start-Process -FilePath $PythonExe -ArgumentList @("-u","-m","uvicorn","app.server:app","--host","127.0.0.1","--port","8010") + $reloadFlag -WindowStyle Hidden -PassThru
$proc.Id | Out-File ".server.pid" -Encoding ASCII
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
        Write-Host "  Public URL: $url" -ForegroundColor Green
        Write-Host ""
    }
}

Write-Host "Local URL: http://127.0.0.1:8010" -ForegroundColor Cyan
Write-Host "Press any key to close this window. To stop later, run: Stop-Process -Id (Get-Content .server.pid)" -ForegroundColor Yellow

# Keep window open
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
