@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ========================================
echo   Prediction Bot - 一键安装
echo ========================================
echo.

echo [1/3] 创建虚拟环境...
python -m venv .venv
if %errorlevel% neq 0 (
    echo 虚拟环境创建失败，请检查 Python 是否已安装
    pause
    exit /b 1
)
echo 虚拟环境创建完成！

echo.
echo [2/3] 安装 Python 依赖...
call .\.venv\Scripts\pip install -r requirements.txt -q -i https://mirrors.aliyun.com/pypi/simple/
if %errorlevel% neq 0 (
    echo 依赖安装失败
    pause
    exit /b 1
)
echo 依赖安装完成！

echo.
echo [3/3] 安装 Playwright 浏览器（约180MB，请耐心等待）...
set PLAYWRIGHT_DOWNLOAD_HOST=https://npmmirror.com/mirrors/playwright/
call .\.venv\Scripts\python.exe -m playwright install --force chromium
if %errorlevel% neq 0 (
    echo ========================================
    echo Playwright 浏览器安装失败
    echo 请手动执行: .\.venv\Scripts\python.exe -m playwright install --force chromium
    echo ========================================
    pause
    exit /b 1
)

echo.
if not exist ".env" (
    copy ".env.example" ".env" >nul
    echo 已创建 .env 文件，请填入飞书 App ID 和 Secret
)

echo.
echo ========================================
echo   安装完成！
echo   双击 start.bat 或 start.vbs 即可启动
echo ========================================
pause
