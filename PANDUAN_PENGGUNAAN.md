# Panduan Pengguna: AlphaHunter IDX Workstation
Selamat datang di pedoman penggunaan **AlphaHunter IDX Workstation**, platform analisis pasar saham bursa Indonesia (IDX) berbasis kecerdasan buatan (AI) kelas premium. 

Platform ini mengintegrasikan pemodelan prediktif machine learning (XGBoost), kalkulator indikator teknikal otomatis, pelacakan Bandarologi (Broker Summary), strategi backtesting, stress testing makroekonomi, sistem simulasi perdagangan (*paper trading*), dan umpan balik model dinamis (*learning engine*) ke dalam satu antarmuka terminal bergaya modern (*dark glassmorphism*).

---

## Daftar Isi
1. [Memulai Aplikasi](#1-memulai-aplikasi)
2. [Dasbor EOD AI Screener](#2-dasbor-eod-ai-screener)
3. [Analisis Bandarologi (Broker Summary)](#3-analisis-bandarologi-broker-summary)
4. [Grafik Interaktif & Indikator Teknikal](#4-grafik-interaktif--indikator-teknikal)
5. [Watchlist & AI Multi-Factor Scorer](#5-watchlist--ai-multi-factor-scorer)
6. [Stress Testing Makroekonomi](#6-stress-testing-makroekonomi)
7. [Komparasi Saham Side-by-Side](#7-komparasi-saham-side-by-side)
8. [Virtual Portfolio & Paper Trading](#8-virtual-portfolio--paper-trading)
9. [Backtest Engine & Skenario Holding](#9-backtest-engine--skenario-holding)
10. [AI Learning Engine & Retraining](#10-ai-learning-engine--retraining)
11. [Ekspor Laporan (CSV & PDF)](#11-ekspor-laporan-csv--pdf)

---

## 1. Memulai Aplikasi
Platform berjalan di lingkungan lokal Anda dan terbagi menjadi dua bagian:
* **Backend API (FastAPI)**: Berjalan pada `http://localhost:8000` dengan database SQLite `alphahunter.db`.
* **Frontend Dashboard (Vite React)**: Berjalan pada `http://localhost:5173`.

> [!NOTE]
> Pembaruan data otomatis (*data ingestion*) menggunakan script orchestrator harian `run_pipeline.py`. Anda dapat memicunya langsung dari tombol **Update AI Predictions** di pojok kanan atas dasbor.

---

## 2. Dasbor EOD AI Screener
Menu utama dasbor menampilkan klasemen **Top 10 Picks** saham untuk keesokan harinya (T+1).
* **XGBoost Probability**: Kolom **Probability (Up)** menunjukkan peluang probabilitas arah pergerakan harga akan ditutup positif besok berdasarkan 21 fitur rekayasa data.
* **Classic Patterns**: Kolom **Patterns** menampilkan hasil pemindaian pola candlestick (seperti `Doji`, `Hammer`, `Bullish/Bearish Engulfing`, `Morning Star`).
* **Bandarologi Badges**: Kolom **Bandarologi** menampilkan status transaksi akumulasi bandar (seperti `Big Accumulation`, `Accumulation`, `Neutral`, `Distribution`, `Big Distribution`).
* **Regime IHSG**: Di pojok kiri atas, terdapat panel status pasar yang mendeteksi pergerakan Indeks Harga Saham Gabungan (`^JKSE`) menggunakan EMA 50/200 dan volatilitas ATR untuk memberikan arahan strategi yang relevan (*Bull, Bear, Sideways, Correction*).

---

## 3. Analisis Bandarologi (Broker Summary)
Bandarologi adalah fitur utama untuk mendeteksi pergerakan dana besar (*Smart Money*) pada saham lapis dua dan tiga (*mid-cap*). Panel ini muncul di sisi kanan grafik saat Anda mengklik salah satu baris saham:
* **Accumulation Ratio**: Persentase kekuatan akumulasi Top 3 Buyer terhadap total transaksi harian. Semakin tinggi persentase, semakin besar akumulasi bandar.
* **Net Foreign Flow**: Nominal bersih beli/jual investor asing dalam Rupiah (Juta atau Miliar).
* **Top 5 Buyers & Top 5 Sellers Table**: Menampilkan kode broker sekuritas Indonesia (seperti `OD`, `YP`, `DX`) dan nilai net transaksi mereka secara real-time.
* **15-Day Trend Chart**: Grafik garis mini SVG di bagian bawah yang memplot pergerakan kekuatan skor akumulasi saham tersebut selama 15 hari terakhir.

---

## 4. Grafik Interaktif & Indikator Teknikal
Workstation menggunakan teknologi **TradingView Lightweight Charts** untuk menampilkan pergerakan harga historis 100 hari (Candlestick dan histogram Volume):
* **SMA Overlay**: Centang pilihan **Show SMA Overlay (5, 20, 50)** untuk memplot garis Simple Moving Average 5 (Cyan), 20 (Oranye), dan 50 (Hijau) langsung pada grafik.
* **Bollinger Bands**: Centang pilihan **Show Bollinger Bands** untuk menggambarkan pita volatilitas atas, tengah, dan bawah guna mendeteksi area jenuh beli/jual.

---

## 5. Watchlist & AI Multi-Factor Scorer
Menu **Watchlist Scorer** memungkinkan Anda membuat daftar pantau saham kustom dengan bobot penilaian dinamis:
* **Preset Bobot**: Pilih salah satu preset di panel Custom Weights:
  * *Balanced* (Bobot merata)
  * *Technical* (30% Teknis)
  * *Value* (Fokus fundamental PER & ROE)
  * *Momentum* (Fokus pada tren jangka pendek)
* **Pencarian & Penambahan Saham**: Ketik kode saham atau nama emiten pada kotak pencarian berfitur autocomplete untuk menambahkannya ke watchlist aktif.
* **Composite Score**: Skor agregat (0-100) dan klasifikasi kelayakan investasi (`Strong`, `Good`, `Neutral`, `Avoid`) akan otomatis dihitung secara real-time berdasarkan bobot kustom Anda.
* **Factor Breakdown Card**: Mengklik saham di watchlist akan memuat 5 kartu perkembangan indikator secara detail (Teknis, Fundamental, Sentimen, Risiko, dan Katalis).

---

## 6. Stress Testing Makroekonomi
Gunakan fitur stress testing di bawah watchlist untuk menyimulasikan dampak kejutan makroekonomi terhadap saham pantauan Anda:
* **Skenario Shock**:
  * **BI Rate Hike & Inflation Shock**: Menurunkan nilai saham sektor properti/teknologi secara drastis, sedangkan sektor keuangan (perbankan) relatif stabil.
  * **Global Commodity Collapse**: Memangkas skor emiten komoditas tambang batubara/energi, namun menaikkan skor emiten transportasi/konsumer karena efisiensi biaya bahan bakar.
  * **Systemic Market Crash (IHSG -5%)**: Menguji ketahanan portofolio terhadap kejatuhan pasar secara sistemik berdasarkan koefisien Beta emiten.
* **Delta Display**: Tabel watchlist akan menampilkan perubahan skor dasar ke skor skenario (contoh: `GJTL 64.5 → 54.5 (-10.0)`).
* **Portfolio Warning Banner**: Memberikan ringkasan peringatan dampak global (seperti *Severe Impact* atau *Minimal Impact*) berdasarkan rata-rata delta watchlist Anda.

---

## 7. Komparasi Saham Side-by-Side
Bandingkan parameter fundamental dan teknikal beberapa saham secara horizontal:
* Centang kotak selektor di samping kiri kode saham pada tabel watchlist (maksimal 3 saham sekaligus).
* Panel komparasi horizontal akan otomatis muncul di bawah watchlist, menyandingkan harga, skor AI, rasio PER, profitabilitas ROE, sensitivitas makroekonomi, dan status akumulasi Bandarologi secara sejajar.

---

## 8. Virtual Portfolio & Paper Trading
Sistem simulasi perdagangan virtual untuk menguji strategi tanpa menggunakan uang riil:
* **Modal Awal**: Saldo tunai virtual sebesar **Rp 100.000.000,00**.
* **Eksekusi Transaksi**: Klik tombol **Beli** atau **Jual** di samping baris saham untuk memunculkan modal transaksi:
  * Pembelian tervalidasi terhadap kecukupan saldo kas tunai.
  * Penjualan tervalidasi terhadap kepemilikan jumlah lot saham yang dimiliki.
* **Dashboard Portfolio**: Tab khusus untuk memantau:
  * *Total Portfolio Value* (Kas + valuasi nilai aset saham saat ini).
  * *Unrealized P&L* (Keuntungan/kerugian mengambang berdasarkan fluktuasi harga).
  * *Realized P&L* (Keuntungan/kerugian bersih yang telah direalisasikan dari penjualan).
  * *Win-Rate* (Rasio rasional transaksi yang menghasilkan profit terhadap total transaksi tertutup).

---

## 9. Backtest Engine & Skenario Holding
Mengevaluasi efisiensi strategi Top Picks XGBoost di masa lalu menggunakan data historis:
* Klik tombol **RUN BACKTEST** di bagian bawah dasbor untuk memproses 100 hari perdagangan terakhir.
* **Holding Slices**: Menampilkan hasil evaluasi jika Anda membeli saham EOD Picks dan menahannya selama **T+1, T+3, T+5, atau T+10** hari kerja.
* **Metrik Evaluasi**: Menghitung *Total Return (%), Win Rate (%),* dan *Max Drawdown (%)* untuk membantu Anda memilih skenario penahanan terbaik yang cocok dengan gaya trading Anda.

---

## 10. AI Learning Engine & Retraining
Menu **AI Learning Engine** adalah pusat pemantauan performa kecerdasan buatan platform:
* **SVG Performance Chart**: Memplot kurva akurasi harian *Rolling Hit Rate* (tebakan naik/turun) dan *Precision@10* (ketepatan rekomendasi Top 10) selama 30 hari ke belakang.
* **Feature Importances**: Grafik bar horizontal yang menunjukkan variabel mana yang paling berpengaruh bagi model XGBoost dalam menentukan pergerakan harga saham (seperti nilai transaksi, volume, dan deviasi indikator).
* **Retraining Logs & Champion Promotion**: Menampilkan riwayat pelatihan otomatis. Jika akurasi rolling 5 hari model drop di bawah **52%**, backend akan otomatis melatih ulang model baru menggunakan data pasar historis terbaru dan menobatkan model terbaik sebagai status *Champion*.

---

## 11. Ekspor Laporan (CSV & PDF)
Simpan dan bagikan laporan hasil analisis harian Anda dengan mudah:
* **Download Report (CSV)**: Klik tombol ini untuk langsung mengunduh berkas tabel spreadsheet `.csv` berisi daftar peringkat lengkap, skor detail, sinyal pola, dan status Bandarologi semua emiten.
* **Print Report (PDF)**: Klik tombol ini untuk membuka jendela pencetakan browser. Lembar cetak telah dioptimalkan secara otomatis menggunakan aturan CSS cetak (*print media rules*) untuk menghilangkan elemen navigasi samping dan tombol aksi, menghasilkan rangkuman dokumen lanskap A4 yang rapi dan siap cetak atau disimpan sebagai PDF.
