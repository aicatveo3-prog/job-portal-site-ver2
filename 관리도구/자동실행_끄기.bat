@echo off
chcp 65001 >nul
cd /d "%~dp0.."
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0..\src\scripts\unregister_scheduler.ps1"
echo.
pause
