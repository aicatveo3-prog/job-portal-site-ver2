@echo off
chcp 65001 >nul
set PYTHONDONTWRITEBYTECODE=1
cd /d "%~dp0"
echo =========================================================
echo  고양시·서울·경기·재택 장애인 채용공고 수동 수집 시작
echo  (OpenCode DeepSeek 4.1 정제 + PDF/HWP 첨부 분석 + 자동 배포)
echo =========================================================
echo.
python scripts\run_daily.py --force
echo.
echo 수집이 완료되었습니다! 사이트를 열려면 아무 키나 누르세요.
pause >nul
start "" "%~dp0docs\index.html"
