@echo off
setlocal
title AlphaHunter IDX - Starting...

echo.
echo ============================================================
echo    AlphaHunter IDX - Auto Start System
echo    Bursa Efek Indonesia Workstation
echo ============================================================
echo.

:: ─────────────────────────────────────────────
:: [1] Cek venv backend
:: ─────────────────────────────────────────────
echo [1/4] Mengecek virtual environment Python...
if not exist "%~dp0backend\venv\Scripts\activate.bat" (
    echo.
    echo [ERROR] Virtual environment tidak ditemukan!
    echo [ERROR] Jalankan setup.bat terlebih dahulu.
    echo.
    pause
    exit /b 1
)
echo [OK] Virtual environment ditemukan.

:: ─────────────────────────────────────────────
:: [2] Cek node_modules
:: ─────────────────────────────────────────────
echo [2/4] Mengecek Node.js packages...
if not exist "%~dp0frontend\node_modules" (
    echo.
    echo [ERROR] node_modules tidak ditemukan!
    echo [ERROR] Jalankan setup.bat terlebih dahulu.
    echo.
    pause
    exit /b 1
)
echo [OK] Node.js packages ditemukan.

:: ─────────────────────────────────────────────
:: [3] Jalankan Backend FastAPI (window baru)
:: ─────────────────────────────────────────────
echo [3/4] Menjalankan Backend FastAPI di port 8000...
start "AlphaHunter-Backend" cmd /k "title AlphaHunter - Backend (FastAPI :8000) && call "%~dp0backend\venv\Scripts\activate.bat" && cd /d "%~dp0backend" && uvicorn app.main:app --reload --host 127.0.0.1 --port 8000"

echo Menunggu backend siap...
ping -n 4 127.0.0.1 >nul

:: ─────────────────────────────────────────────
:: [4] Jalankan Frontend Vite (window baru)
:: ─────────────────────────────────────────────
echo [4/4] Menjalankan Frontend Vite React di port 5173...
start "AlphaHunter-Frontend" cmd /k "title AlphaHunter - Frontend (Vite :5173) && cd /d "%~dp0frontend" && npm run dev"

echo Menunggu frontend siap...
ping -n 4 127.0.0.1 >nul

:: ─────────────────────────────────────────────
:: [5] Buka browser
:: ─────────────────────────────────────────────
echo.
echo ============================================================
echo  Backend  : http://localhost:8000
echo  Frontend : http://localhost:5173
echo  API Docs : http://localhost:8000/docs
echo ============================================================
echo.
echo Membuka browser di http://localhost:5173 ...
start "" "http://localhost:5173"

echo.
echo Kedua server berjalan di window terpisah.
echo Tutup window Backend dan Frontend untuk menghentikan server.
echo Atau jalankan stop.bat untuk menutup semua sekaligus.
echo.
pause
endlocal
