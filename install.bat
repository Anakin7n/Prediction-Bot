@echo off
cd /d "%~dp0"
pip install -r requirements.txt -q
echo 依赖安装完成！
pause
