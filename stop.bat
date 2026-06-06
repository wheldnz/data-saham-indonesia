@echo off
setlocal
title AlphaHunter IDX - Stopping...

echo.
echo ============================================================
echo    AlphaHunter IDX - Menghentikan Semua Server
echo ============================================================
echo.

echo [1/2] Menghentikan Backend (uvicorn / Python)...
taskkill /F /FI "WINDOWTITLE eq AlphaHunter-Backend*" >nul 2>&1
for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr ":8000 " ^| findstr "LISTENING"') do (
    taskkill /F /PID %%a >nul 2>&1
)
echo [OK] Backend dihentikan.

echo [2/2] Menghentikan Frontend (Vite / Node)...
taskkill /F /FI "WINDOWTITLE eq AlphaHunter-Frontend*" >nul 2>&1
for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr ":5173 " ^| findstr "LISTENING"') do (
    taskkill /F /PID %%a >nul 2>&1
)
echo [OK] Frontend dihentikan.

echo.
echo ============================================================
echo   Semua server AlphaHunter IDX telah dihentikan.
echo ============================================================
echo.
pause
endlocal
