@echo off
setlocal
cd /d "%~dp0"

if not exist "start.ps1" (
    echo Put this file in the same folder as start.ps1, then run it again.
    pause
    exit /b 1
)

if exist ".venv\Scripts\python.exe" (
    set "BOT_PY=%~dp0.venv\Scripts\python.exe"
) else (
    set "BOT_PY=python"
)

echo Checking pip...
"%BOT_PY%" -c "import pip._internal.commands.install" >nul 2>&1
if errorlevel 1 goto repair_pip
goto install_playwright

:repair_pip
if not exist ".venv\Scripts\python.exe" (
    echo pip is broken in system Python. No project virtual environment was found.
    goto failed
)
echo pip is damaged. Repairing it from Python's bundled installer...
"%BOT_PY%" -c "import ensurepip,os,pathlib,subprocess,sys; d=pathlib.Path(ensurepip.__file__).parent/'_bundled'; w=next(d.glob('pip-*.whl')); e=os.environ.copy(); e['PYTHONPATH']=str(w); sys.exit(subprocess.call([sys.executable,'-m','pip','install','--no-index','--find-links',str(d),'--force-reinstall','pip'],env=e))"
if errorlevel 1 goto failed
"%BOT_PY%" -c "import pip._internal.commands.install"
if errorlevel 1 goto failed

:install_playwright
echo Installing Playwright into the Python environment used by the bot...
"%BOT_PY%" -m pip install -i https://mirrors.aliyun.com/pypi/simple/ "playwright>=1.40"
if errorlevel 1 goto failed

"%BOT_PY%" -c "from playwright.sync_api import sync_playwright; print('Playwright import OK')"
if errorlevel 1 goto failed

echo.
echo Installation succeeded. Restart the bot and try again.
pause
exit /b 0

:failed
echo.
echo Installation or import failed. Send the error text from this window back for diagnosis.
pause
exit /b 1
