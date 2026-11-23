@echo off
chcp 65001 >nul
set PYTHONDONTWRITEBYTECODE=1
cd /d "%~dp0.."
echo =========================================================
echo  카카오톡 '나에게 보내기' 연결 / 토큰 재발급
echo  브라우저가 열리면 카카오 로그인 및 동의를 완료해 주세요.
echo =========================================================
echo.
python -u scripts\setup_kakao.py --open
echo.
pause
