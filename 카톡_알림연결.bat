@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo =========================================================
echo  카카오톡 '나에게 보내기' 최초 1회 연결
echo  브라우저가 열리면 카카오 로그인 및 동의를 완료해 주세요.
echo =========================================================
echo.
python -u scripts\setup_kakao.py --open
echo.
pause
