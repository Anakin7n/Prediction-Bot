@echo off
chcp 65001 >nul
where wt >nul 2>&1 && (start wt powershell -NoExit -Command "& '%~dp0start.ps1'") || (start powershell -NoExit -Command "& '%~dp0start.ps1'")
