Set-Location (Split-Path -Parent $MyInvocation.MyCommand.Path)

if (Test-Path ".\.venv\Scripts\python.exe") {
    Write-Host "[venv] Starting bot..." -ForegroundColor Green
    .\.venv\Scripts\python.exe main.py
} else {
    Write-Host "[system] Starting bot..." -ForegroundColor Green
    python main.py
}
