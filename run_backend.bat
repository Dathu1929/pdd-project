@echo off
title Smart Electricity Backend Server
echo ==============================================
echo   Starting Smart Electricity Backend Server...
echo ==============================================
cd backend
python -m uvicorn server:app --host 0.0.0.0 --port 8000
pause
