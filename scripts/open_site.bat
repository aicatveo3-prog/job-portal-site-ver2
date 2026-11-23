@echo off
chcp 65001 >nul
cd /d "%~dp0.."
echo ===================================================
echo  고양시·수도권 장애인 채용공고 사이트 실행 중...
echo  브라우저가 자동으로 열립니다: http://localhost:8080
echo  (이 창을 닫으면 로컬 서버가 종료됩니다)
echo ===================================================
start "" http://localhost:8080
python -m http.server 8080 -d docs
