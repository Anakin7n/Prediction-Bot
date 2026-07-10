Set-Location (Split-Path -Parent $MyInvocation.MyCommand.Path)

if (Test-Path ".\.venv\Scripts\python.exe") {
    $python = ".\.venv\Scripts\python.exe"
    Write-Host "[.venv] Starting bot (auto-restart)..." -ForegroundColor Green
} else {
    $python = "python"
    Write-Host "[system python] Starting bot (auto-restart)..." -ForegroundColor Green
}

while ($true) {
    & $python main.py
    Write-Host "[guard] 进程退出，5 秒后自动重启（关闭此窗口可停止）..." -ForegroundColor Yellow
    Start-Sleep -Seconds 5
}
