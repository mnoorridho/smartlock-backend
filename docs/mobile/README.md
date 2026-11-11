# Dashboard mobile terintegrasi

Shell dashboard ada di `app/static_pages/dashboard.html` dan tetap disajikan oleh
route FastAPI `/dashboard`. Aset Face Unlock dipisahkan menjadi `face-unlock.css`,
`face-unlock-core.js`, dan `face-unlock.js` melalui `/dashboard-assets/`.
Presentasi halaman user berada di `user-portal.js` dan `user-portal.css`, memakai
token warna, tipografi, ikon SVG, dan komponen dashboard owner yang sama.
Tidak memerlukan build frontend. Lihat [panduan Face Unlock](FACE_UNLOCK.md)
untuk migrasi dan batas akurasi verifikasi. Lihat [portal user dan batas peran](USER_ROLES.md)
untuk pendaftaran sendiri, persetujuan owner, dan izin metode akses.
Halaman tamu `/guest/{token}` adalah halaman terpisah dan tidak diubah.

## Menjalankan

Untuk backend dengan **database uji lokal terpisah**, langkah daftar/login, akses
desktop/HP, firewall, dan HTTPS kamera/GPS, ikuti [panduan backend uji](LOCAL_TEST.md).
Mode ini memakai port 8000, menyimpan data uji sendiri, dan menonaktifkan MQTT.

Mode demo tanpa login dan data dummy bawaan telah dihapus. Gunakan backend
port 8000 dan login akun Anda; parameter URL demo lama tidak membuka dashboard.
Akun uji/perangkat virtual yang dibuat di backend tetap merupakan data uji tersimpan,
terpisah dari data dummy frontend yang sudah dihapus.

### Login dengan akun asli

Jalankan backend FastAPI, lalu buka `/dashboard`. Pilih **Daftar Akun**, isi nama,
email, dan password minimal 6 karakter, lalu pilih **Masuk** dengan email/password
yang sama. Akun pertama menjadi owner; akun berikutnya memerlukan izin dari owner
untuk melihat perangkat. Tidak ada username/password bawaan.

Untuk Google, backend membaca `GOOGLE_CLIENT_ID` dari `.env` di root proyek,
terlepas dari working directory. Setelah konfigurasi berubah, restart backend.
Email Google harus sudah terdaftar dan aktif di Smart Lock. Lihat langkah OAuth
dan Authorized JavaScript origins pada README utama. Server preview bukan server
login Google; gunakan origin backend yang terdaftar.

Virtual environment `venv` yang disertakan saat ini merujuk Python 3.12 di komputer
asal sehingga tidak dapat dijalankan pada komputer ini. Buat environment baru
dengan Python yang terpasang, tanpa menghapus folder lama:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Database PostgreSQL dan migrasi harus sudah disiapkan sesuai README utama sebelum
login akun asli. Mode SQLite uji terpisah sudah memverifikasi daftar/login dan
izin owner/user. Autentikasi Google dan hardware fisik belum diuji pada penyiapan ini.

Ikuti konfigurasi database, environment, dependency, dan migrasi di README utama.
Dari folder proyek yang berisi `app/`, jalankan pada Windows:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Buka `http://localhost:8000/dashboard` pada komputer. Untuk mengakses lewat HP,
gunakan origin HTTPS backend yang sudah tersedia atau alamat IP LAN komputer
dengan port 8000 pada jaringan yang sama. Fitur GPS memerlukan secure context
(HTTPS pada perangkat lain). Refresh dashboard setelah menyimpan perubahan HTML.


## Orientasi layar dan QR akses Web App

- **HP:** layout menggunakan susunan portrait. Jika HP diputar ke landscape,
  aplikasi menampilkan instruksi untuk kembali ke portrait; aplikasi tidak
  memaksa perangkat memutar layar secara fisik.
- **Laptop/PC:** layout desktop memakai ruang horizontal (landscape). Laptop
  layar sentuh tetap memakai layout desktop selama lebar viewport mencukupi.
- Pada layar login desktop tersedia QR Code untuk membuka `/dashboard` dari HP.
  Setelah login, tombol **QR HP** di topbar membuka QR yang sama.
- QR dibuat dinamis dari origin yang sedang dibuka (`origin + /dashboard`),
  sehingga tidak menanam URL ngrok lama. Jika halaman dibuka melalui localhost,
  QR hanya akan menunjuk ke localhost dan tidak dapat dipakai dari HP. Gunakan
  IP LAN pada jaringan Wi-Fi yang sama atau URL HTTPS tunnel/hosting yang aktif.
- QR Web App berbeda dari QR Akses Tamu. QR Web App membuka halaman login/dashboard;
  QR Akses Tamu tetap membuka `/guest/{token}` dan memerlukan PIN sesuai alur tamu.

## Perilaku

- Warna, tipografi, ikon SVG, tema gelap/terang, sesi login, router, dan endpoint API
  mengikuti implementasi desktop yang sama.
- Viewport sampai 768 px memakai layout mobile. User-Agent, mobile client hint, dan
  kemampuan sentuh membantu mempertahankan layout mobile ketika HP diputar.
  Laptop dengan layar sentuh tetap memakai desktop pada viewport lebar.
- Overview, Devices, dan Access Logs tersedia di menu bawah. Lainnya membuka drawer
  untuk Permissions, NFC, Akses Tamu, Pengaturan, dan logout sesuai role sebelumnya.
- Drawer mendukung backdrop, Escape, pengembalian fokus, dan pembatasan fokus keyboard.
  Navigasi mobile tidak ditampilkan pada layar login.
- Kartu ringkasan mobile memakai grid dua kolom tanpa geser; ringkasan NFC/riwayat
  tersusun vertikal. Daftar perangkat tetap memakai scroll horizontal native dan CSS scroll snap.
  Tabel yang dimuat belakangan juga dibungkus area scroll tanpa melebarkan halaman.
- Tombol dan area toggle memiliki target sentuh minimal 44 × 44 CSS px. Layout
  memperhitungkan safe area dan ruang menu bawah; input 16 px mencegah zoom saat diketik.
- Pada perangkat mobile landscape, konten disembunyikan dan dibuat inert. Overlay
  memenuhi layar dengan animasi HP serta pesan portrait yang diminta. Media query
  `max-width:932px` dan `orientation:landscape` dilengkapi pemeriksaan orientasi JS
  untuk perangkat yang lebih lebar. Ukuran viewport desktop landscape tidak diblokir.
- `screen.orientation.lock('portrait')` dicoba setelah interaksi dan saat fullscreen
  berubah. Browser dapat menolaknya; overlay tetap menjadi pengaman ketika penguncian
  orientasi fisik tidak diizinkan. Preferensi reduced motion menonaktifkan animasi.

## Verifikasi

`scripts/check_mobile_dashboard.cjs` memakai Playwright dengan API simulasi. Tes
memeriksa viewport 320 px, mobile portrait/landscape, desktop, perubahan ukuran layar,
laptop sentuh, navigasi, role owner/user, target sentuh menu bawah, scroll kartu,
tabel asinkron, kedua tema, logout, kontinuitas URL, overflow, dan error JavaScript.
Tes memblokir CDN dan mengganti dependensi peta/pemilih tanggal dengan stub; integrasi
GPS, peta, Google login, backend nyata, dan perangkat fisik tidak diuji oleh skrip ini.

Dengan Node.js serta Playwright dan browser tersedia:

```powershell
node scripts/check_mobile_dashboard.cjs
```

Untuk Microsoft Edge yang sudah terpasang:

```powershell
$env:PLAYWRIGHT_CHANNEL = 'msedge'
node scripts/check_mobile_dashboard.cjs
```

Tes menyimpan pratinjau di folder ini: `mobile-preview.png`,
`mobile-landscape-preview.png`, dan `desktop-preview.png`. Pratinjau memakai data
simulasi dan font fallback karena CDN diblokir pada tes terisolasi.
