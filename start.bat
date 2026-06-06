@echo off
chcp 65001 >nul
title AlphaHunter IDX — Starting...
color 0A

echo.
echo  ╔══════════════════════════════════════════════════════╗
echo  ║         AlphaHunter IDX - Auto Start System         ║
echo  ║             Bursa Efek Indonesia Workstation         ║
echo  ╚══════════════════════════════════════════════════════╝
echo.

:: ─────────────────────────────────────────────
:: [1] Cek apakah venv backend sudah ada
:: ─────────────────────────────────────────────
echo  [1/4] Mengecek virtual environment Python...
if not exist "%~dp0backend\venv\Scripts\activate.bat" (
    echo.
    echo  [!] Virtual environment tidak ditemukan!
    echo  [!] Jalankan setup.bat terlebih dahulu untuk instalasi awal.
    echo.
    pause
    exit /b 1
)
echo  [OK] Virtual environment ditemukan.

:: ─────────────────────────────────────────────
:: [2] Cek apakah node_modules frontend sudah ada
:: ─────────────────────────────────────────────
echo  [2/4] Mengecek Node.js packages...
if not exist "%~dp0frontend\node_modules" (
    echo.
    echo  [!] node_modules tidak ditemukan!
    echo  [!] Jalankan setup.bat terlebih dahulu untuk instalasi awal.
    echo.
    pause
    exit /b 1
)
echo  [OK] Node.js packages ditemukan.

:: ─────────────────────────────────────────────
:: [3] Jalankan Backend FastAPI (window baru)
:: ─────────────────────────────────────────────
echo  [3/4] Menjalankan Backend FastAPI di port 8000...
start "AlphaHunter - Backend (FastAPI)" cmd /k "chcp 65001 >nul && color 0B && title AlphaHunter - Backend (FastAPI :8000) && echo  [Backend] Mengaktifkan virtual environment... && call ""%~dp0backend\venv\Scripts\activate.bat"" && echo  [Backend] Menjalankan uvicorn... && cd /d ""%~dp0backend"" && uvicorn app.main:app --reload --host 127.0.0.1 --port 8000"

:: Tunggu 3 detik agar backend sempat start
timeout /t 3 /nobreak >nul

:: ─────────────────────────────────────────────
:: [4] Jalankan Frontend Vite React (window baru)
:: ─────────────────────────────────────────────
echo  [4/4] Menjalankan Frontend Vite React di port 5173...
start "AlphaHunter - Frontend (Vite)" cmd /k "chcp 65001 >nul && color 0D && title AlphaHunter - Frontend (Vite :5173) && echo  [Frontend] Menjalankan npm dev server... && cd /d ""%~dp0frontend"" && npm run dev"

:: Tunggu 3 detik agar frontend sempat start
timeout /t 3 /nobreak >nul

:: ─────────────────────────────────────────────
:: [5] Buka browser otomatis
:: ─────────────────────────────────────────────
echo.
echo  ╔══════════════════════════════════════════════════════╗
echo  ║   ✓  Backend  : http://localhost:8000               ║
echo  ║   ✓  Frontend : http://localhost:5173               ║
echo  ║   ✓  API Docs : http://localhost:8000/docs          ║
echo  ╚══════════════════════════════════════════════════════╝
echo.
echo  Membuka browser...
timeout /t 2 /nobreak >nul
start "" "http://localhost:5173"

echo.
echo  [INFO] Kedua server sudah berjalan di window terpisah.
echo  [INFO] Tutup window Backend dan Frontend untuk menghentikan server.
echo  [INFO] Atau jalankan stop.bat untuk menutup semua sekaligus.
echo.
pause
