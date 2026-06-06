@echo off
chcp 65001 >nul
title AlphaHunter IDX — Setup Awal
color 0E

echo.
echo  ╔══════════════════════════════════════════════════════╗
echo  ║        AlphaHunter IDX - Setup Instalasi Awal       ║
echo  ║    Jalankan ini SEKALI setelah clone dari GitHub     ║
echo  ╚══════════════════════════════════════════════════════╝
echo.
echo  Script ini akan:
echo    1. Membuat Python virtual environment (venv)
echo    2. Install semua dependensi Python (FastAPI, uvicorn, dll)
echo    3. Install semua dependensi Node.js (React, Vite, dll)
echo    4. Menjalankan pipeline awal untuk download data 941 emiten IDX
echo    5. Melatih model AI pertama kali
echo.
echo  ─────────────────────────────────────────────────────
echo  PERINGATAN: Proses pipeline awal (langkah 4) akan
echo  memakan waktu 10-30 menit tergantung koneksi internet!
echo  ─────────────────────────────────────────────────────
echo.
set /p confirm="Lanjutkan setup? (Y/N): "
if /i not "%confirm%"=="Y" (
    echo  Setup dibatalkan.
    pause
    exit /b 0
)

:: ─────────────────────────────────────────────
:: Cek Python tersedia
:: ─────────────────────────────────────────────
echo.
echo  [1/5] Mengecek instalasi Python...
python --version >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo  [ERROR] Python tidak ditemukan di PATH!
    echo  [ERROR] Unduh dan install Python 3.10+ dari: https://www.python.org/downloads/
    echo  [ERROR] Pastikan centang "Add Python to PATH" saat instalasi.
    pause
    exit /b 1
)
for /f "tokens=*" %%v in ('python --version 2^>^&1') do echo  [OK] Ditemukan: %%v

:: ─────────────────────────────────────────────
:: Cek Node.js tersedia
:: ─────────────────────────────────────────────
echo.
echo  [2/5] Mengecek instalasi Node.js...
node --version >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo  [ERROR] Node.js tidak ditemukan di PATH!
    echo  [ERROR] Unduh dan install Node.js LTS dari: https://nodejs.org/
    pause
    exit /b 1
)
for /f "tokens=*" %%v in ('node --version 2^>^&1') do echo  [OK] Ditemukan Node.js %%v

:: ─────────────────────────────────────────────
:: Setup Backend Python venv
:: ─────────────────────────────────────────────
echo.
echo  [3/5] Menyiapkan Backend Python...
cd /d "%~dp0backend"

if not exist "venv" (
    echo  Membuat virtual environment...
    python -m venv venv
    if %ERRORLEVEL% neq 0 (
        echo  [ERROR] Gagal membuat virtual environment!
        pause
        exit /b 1
    )
    echo  [OK] Virtual environment dibuat.
) else (
    echo  [OK] Virtual environment sudah ada, dilewati.
)

echo  Menginstall dependensi Python (ini mungkin butuh beberapa menit)...
call "%~dp0backend\venv\Scripts\activate.bat"
pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet
if %ERRORLEVEL% neq 0 (
    echo  [ERROR] Gagal menginstall dependensi Python!
    echo  [ERROR] Cek koneksi internet dan coba lagi.
    pause
    exit /b 1
)
echo  [OK] Dependensi Python berhasil diinstall.

:: ─────────────────────────────────────────────
:: Setup Frontend Node.js
:: ─────────────────────────────────────────────
echo.
echo  [4/5] Menyiapkan Frontend Node.js...
cd /d "%~dp0frontend"

if not exist "node_modules" (
    echo  Menginstall packages Node.js (ini mungkin butuh beberapa menit)...
    npm install
    if %ERRORLEVEL% neq 0 (
        echo  [ERROR] Gagal menginstall dependensi Node.js!
        echo  [ERROR] Cek koneksi internet dan coba lagi.
        pause
        exit /b 1
    )
    echo  [OK] Dependensi Node.js berhasil diinstall.
) else (
    echo  [OK] node_modules sudah ada, dilewati.
)

:: ─────────────────────────────────────────────
:: Jalankan Pipeline Awal (Download Data & Train Model)
:: ─────────────────────────────────────────────
echo.
echo  [5/5] Menjalankan pipeline awal (download data + training AI)...
echo  ─────────────────────────────────────────────────────
echo  Proses ini bisa memakan waktu 10-30 menit.
echo  Jangan tutup window ini!
echo  ─────────────────────────────────────────────────────
echo.
cd /d "%~dp0backend"
call "%~dp0backend\venv\Scripts\activate.bat"
python run_pipeline.py
if %ERRORLEVEL% neq 0 (
    echo.
    echo  [WARNING] Pipeline mengalami error. Cek pesan di atas.
    echo  [WARNING] Anda tetap bisa mencoba menjalankan start.bat,
    echo  [WARNING] namun beberapa data mungkin kosong.
    echo.
) else (
    echo.
    echo  [OK] Pipeline selesai! Data dan model AI siap.
)

:: ─────────────────────────────────────────────
:: Selesai
:: ─────────────────────────────────────────────
echo.
echo  ╔══════════════════════════════════════════════════════╗
echo  ║          ✓  Setup Selesai dengan Sukses!             ║
echo  ║                                                      ║
echo  ║   Selanjutnya, jalankan start.bat untuk              ║
echo  ║   menjalankan aplikasi AlphaHunter IDX.              ║
echo  ╚══════════════════════════════════════════════════════╝
echo.
set /p launch="Jalankan aplikasi sekarang? (Y/N): "
if /i "%launch%"=="Y" (
    call "%~dp0start.bat"
)
pause
