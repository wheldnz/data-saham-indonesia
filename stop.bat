@echo off
chcp 65001 >nul
title AlphaHunter IDX — Stopping...
color 0C

echo.
echo  ╔══════════════════════════════════════════════════════╗
echo  ║          AlphaHunter IDX - Menghentikan Server      ║
echo  ╚══════════════════════════════════════════════════════╝
echo.

:: Hentikan proses uvicorn (backend Python)
echo  [1/2] Menghentikan Backend (uvicorn / Python)...
taskkill /F /FI "WINDOWTITLE eq AlphaHunter - Backend*" >nul 2>&1
:: Fallback: hentikan berdasarkan port 8000
for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr ":8000 " ^| findstr "LISTENING"') do (
    taskkill /F /PID %%a >nul 2>&1
)
echo  [OK] Backend dihentikan.

:: Hentikan proses npm/vite (frontend Node)
echo  [2/2] Menghentikan Frontend (Vite / Node)...
taskkill /F /FI "WINDOWTITLE eq AlphaHunter - Frontend*" >nul 2>&1
:: Fallback: hentikan berdasarkan port 5173
for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr ":5173 " ^| findstr "LISTENING"') do (
    taskkill /F /PID %%a >nul 2>&1
)
echo  [OK] Frontend dihentikan.

echo.
echo  ╔══════════════════════════════════════════════════════╗
echo  ║   ✓  Semua server AlphaHunter IDX telah dihentikan  ║
echo  ╚══════════════════════════════════════════════════════╝
echo.
timeout /t 2 /nobreak >nul
