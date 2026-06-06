# AlphaHunter IDX — AI-Powered Stock Market Analysis Workstation

**AlphaHunter IDX** adalah platform workstation analisis pasar saham terintegrasi yang dirancang khusus untuk Bursa Efek Indonesia (IDX). Menggunakan arsitektur modern berbasis AI, platform ini ditujukan untuk memandu investor dan trader (khususnya pada saham *mid-cap*) dengan data terkuantifikasi, analisis Bandarologi (Broker Summary), strategi backtesting, stress testing makroekonomi, dan simulasi perdagangan virtual.

Platform ini dibangun menggunakan arsitektur decoupled:
* **Backend**: FastAPI (Python 3.12+) dengan ORM SQLAlchemy & database relasional SQLite.
* **Frontend**: React (Vite) dengan CSS Vanilla bergaya *Modern Dark Glassmorphism* yang responsif.

---

## 📁 Struktur Proyek
```text
Data Saham Indonesia/
├── backend/                  # Python FastAPI Backend Service
│   ├── app/
│   │   ├── core/             # Konfigurasi & Kredensial
│   │   ├── db/               # Inisialisasi Database SQLite
│   │   ├── models/           # Skema Tabel SQLAlchemy (Stock, OHLCV, Portfolio, dll)
│   │   └── services/         # Engine Logika (Scoring, Bandarologi, Learning, Scenario)
│   ├── data/                 # Penyimpanan dataset CSV, status JSON, & model XGBoost
│   ├── alembic/              # File migrasi database
│   ├── ingest_data.py        # Pipeline Ingestion (Yahoo Finance Raw API)
│   ├── calculate_features.py # Pipa rekayasa fitur teknikal (Pandas-TA)
│   ├── pattern_scanner.py    # Pemindai pola grafik lilin (vectorized sliding window)
│   ├── predict_tomorrow.py   # AI Inference Engine (XGBoost top picks)
│   ├── run_pipeline.py       # Daily Orchestrator Pipeline
│   ├── requirements.txt      # Python Dependencies
│   └── alphahunter.db        # Database SQLite Fisik (Terbuat otomatis)
│
├── frontend/                 # React Frontend Client
│   ├── src/
│   │   ├── App.jsx           # Kontroler Utama & React Views
│   │   ├── index.css         # Styling Dark Glassmorphism & Print Media Styles
│   │   └── main.jsx          # React Entry Point
│   ├── package.json          # Node Dependencies & Scripts
│   └── vite.config.js        # Konfigurasi Port & HMR Vite
│
├── README.md                 # Dokumentasi Developer (Berkas ini)
└── PANDUAN_PENGGUNAAN.md     # Panduan Operasional Fitur Pengguna
```

---

## 🛠️ Prasyarat (Prerequisites)
Sebelum menjalankan sistem secara lokal, pastikan mesin Anda telah terpasang:
1. **Python 3.10 atau versi di atasnya** (Direkomendasikan Python 3.12).
2. **Node.js LTS** (Versi 18 atau versi di atasnya).
3. **Git** (Untuk mempermudah push repository ke GitHub).

---

## 🚀 Panduan Instalasi & Menjalankan Aplikasi

Ikuti langkah-langkah di bawah ini untuk menjalankan backend dan frontend di mesin lokal Anda secara mandiri:

### Langkah 1: Kloning & Pengaturan Backend (Python FastAPI)

1. Buka Terminal/PowerShell Anda dan arahkan ke direktori proyek `backend`:
   ```bash
   cd "backend"
   ```

2. Buat lingkungan virtual Python (*virtual environment*) untuk mengisolasi dependensi:
   ```bash
   python -m venv venv
   ```

3. Aktifkan virtual environment Anda:
   * **Windows (PowerShell)**:
     ```powershell
     .\venv\Scripts\Activate.ps1
     ```
   * **Windows (CMD)**:
     ```cmd
     .\venv\Scripts\activate.bat
     ```
   * **macOS/Linux**:
     ```bash
     source venv/bin/activate
     ```

4. Pasang semua dependensi Python yang dibutuhkan:
   ```bash
   pip install -r requirements.txt
   ```

5. Jalankan inisialisasi awal database dan unduh data pasar pertama kali (*initial seeding*):
   ```bash
   python run_pipeline.py
   ```
   *Proses ini akan mengunduh data 941 emiten aktif IDX, menghitung indikator teknikal (RSI, Stochastic, Volume SMA), menjalankan algoritma Bandarologi EOD 15 hari, memicu model XGBoost AI untuk menghasilkan Top 10 Prediksi perdana, serta melacak IHSG.*

6. Jalankan Server API Backend FastAPI:
   ```bash
   uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
   ```
   *Server backend sekarang aktif di `http://localhost:8000`. Dokumen API interaktif dapat diakses pada `http://localhost:8000/docs`.*

---

### Langkah 2: Pengaturan Frontend (Vite React Client)

1. Buka tab terminal baru dan arahkan ke direktori proyek `frontend`:
   ```bash
   cd "frontend"
   ```

2. Pasang semua dependensi paket Node.js:
   ```bash
   npm install
   ```

3. Jalankan server pengembangan Vite untuk frontend:
   ```bash
   npm run dev
   ```

4. Buka peramban (*browser*) Anda dan akses tautan berikut:
   ```text
   http://localhost:5173
   ```
   *Terminal Workstation AlphaHunter IDX kini siap digunakan secara penuh!*

---

## 🤖 Penjelasan Mendalam Mengenai Fitur Proyek (Untuk GitHub)

Ketika mengunggah ke GitHub, penting untuk mendokumentasikan keunggulan teknis dibalik setiap fitur utama platform ini:

### 1. Daily Ingestion & Custom Bypass Engine
* **Bypass Rate Limit**: Karena Yahoo Finance membatasi pemanggilan API standar, platform mem-bypass blokir tersebut dengan melakukan *raw HTTP calls* langsung ke *Yahoo Chart API* secara asinkron di [yfinance_client.py](file:///c:/Users/USER/Documents/present/Data%20Saham%20Indonesia/backend/app/services/yfinance_client.py).
* **Incremental Ingestion**: Engine secara otomatis melacak data historis terakhir di database lokal dan hanya mengunduh data baru sejak tanggal tersebut (*Safety window 7 hari*), menghemat durasi pembaruan data dari belasan menit menjadi di bawah 1-2 menit saja.

### 2. Bandarologi (Broker Summary) Engine
* **Skema Transaksi**: Memetakan interaksi transaksi broker dengan membedakan sekuritas Institutional/Smart Money (seperti `OD`, `DX`, `RX`, `KZ`) dan Sekuritas Ritel (seperti `YP`, `XC`, `PD`).
* **Accumulation Ratio**: Rasio matematis dihitung berdasarkan dominasi pembelian bersih oleh Top 3 Broker. Jika volume beli terkonsentrasi pada sekuritas institusi sementara ritel melepas barang, sistem mengklasifikasikannya sebagai `Big Accumulation` atau `Accumulation` (sangat relevan untuk menganalisis pergerakan saham *mid-cap*).

### 3. AI Predictive Model & Self-Retraining Loop
* **Model XGBoost**: Dilatih menggunakan variabel momentum (RSI-7, Stochastic, ATR), akumulasi volume transaksi, dan dinamika harga.
* **Auto-Retrain Mechanism**: [learning_engine.py](file:///c:/Users/USER/Documents/present/Data%20Saham%20Indonesia/backend/app/services/learning_engine.py) mencatat tingkat ketepatan prediksi harian (*Rolling Hit Rate* dan *Precision@10*). Jika akurasi model drop di bawah **52%** selama 5 hari berturut-turut, sistem melatih ulang model secara otomatis di latar belakang untuk menghindari degradasi performa model (*data drift*).

### 4. Macro Stress Testing Simulator
* **Scenario Modelling**: Menyediakan simulasi stres portofolio dinamis di [scenario_analysis.py](file:///c:/Users/USER/Documents/present/Data%20Saham%20Indonesia/backend/app/services/scenario_analysis.py) untuk menyimulasikan dampak makro:
  * *Suku Bunga & Inflasi Naik*: Memberikan beban negatif tinggi pada saham sensitif suku bunga (Properti & Teknologi), namun mengapresiasi bank dengan margin laba tinggi.
  * *Commodity Collapse*: Menjatuhkan performa saham energi/tambang sambil menaikkan performa saham konsumer/transporter.
  * *Systemic Crash*: Mensimulasikan IHSG anjlok -5% dan mengevaluasi penurunan skor berdasarkan sensitivitas Beta sektoral.

### 5. Virtual Paper Trading System
* **Double Ledger Validation**: Sistem mengelola saldo virtual Rp 100 Juta. Setiap eksekusi transaksi di validasi secara ketat pada sisi server [portfolio.py](file:///c:/Users/USER/Documents/present/Data%20Saham%20Indonesia/backend/app/models/portfolio.py) untuk mencegah transaksi ilegal (membeli melebihi saldo kas tunai, atau menjual lot saham melebihi kepemilikan riil).
* **Portfolio Metrics**: Menghitung rata-rata modal pembelian (*Average Buy Price*), keuntungan/kerugian belum direalisasikan (*Unrealized P&L*), keuntungan bersih yang direalisasikan (*Realized P&L*), dan rasio kemenangan transaksi (*Win-Rate*).

### 6. Media Print & Document Exporters
* **CSV Streaming**: Mengekspor data tabel secara instan menggunakan standard format streaming CSV pada FastAPI.
* **Responsive PDF Layout**: Memanfaatkan standard browser print API (`window.print()`) yang dipandu oleh aturan media print CSS (`@media print`) di [index.css](file:///c:/Users/USER/Documents/present/Data%20Saham%20Indonesia/frontend/src/index.css) untuk mereduksi header navigasi dan memformat halaman menjadi landscape A4 yang bersih dari tombol aksi.
