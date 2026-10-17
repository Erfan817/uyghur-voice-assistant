# 一键启动：建 venv、装依赖、跑服务
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)

if (-not (Test-Path '.venv')) {
    python -m venv .venv
}
& .\.venv\Scripts\python.exe -m pip install --upgrade pip --quiet
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt --quiet

$port = if ($env:AYNUR_PORT) { $env:AYNUR_PORT } else { '8000' }
Write-Host "Aynur 启动中： http://127.0.0.1:$port" -ForegroundColor Cyan
& .\.venv\Scripts\python.exe -m uvicorn server.main:app --host 0.0.0.0 --port $port
