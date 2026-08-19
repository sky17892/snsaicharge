@echo off
echo ========================================================
echo  SML FastAPI Backend & Cloudflare Tunnel Starting...
echo ========================================================

:: 1. FastAPI 서버를 새 창에서 실행 (0.0.0.0:8000)
start cmd /k "uvicorn main:app --reload --host 0.0.0.0 --port 8000"

:: 2. 3초 대기 후 Cloudflare Tunnel 터미널 실행
timeout /t 3 /nobreak > nul
npx cloudflared tunnel --url http://0.0.0.0:8000

pause