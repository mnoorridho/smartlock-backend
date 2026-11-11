# Isi paket Smartlock

Kode proyek dan README perubahan terdapat dalam folder ini.

File rahasia (.env, authtoken ngrok), database/referensi wajah lokal, password akun uji,
virtual environment, cache, dan log tidak disertakan.

Setelah ekstrak, buat environment pada komputer tujuan:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Untuk mode SQLite uji + perangkat virtual:

```powershell
.\scripts\start_backend.ps1 -LocalTest
```

Buka http://localhost:8000/dashboard. Database uji pada komputer tujuan akan kosong;
daftarkan akun pertama sebagai owner. Akun, wajah, dan perangkat dari komputer asal
sengaja tidak dibawa dalam ZIP. Baca perubahan web app mobile.md dan docs/mobile/LOCAL_TEST.md.

Untuk PostgreSQL, isi .env dan tinjau/jalankan migrasi sebelum menjalankan backend biasa.
Ngrok harus dipasang dan dihubungkan dengan authtoken Anda sendiri pada komputer tujuan.


## QR Web App

QR untuk membuka Web App dibuat dinamis dari alamat aktif ditambah `/dashboard`.
Di laptop, QR tampil pada halaman login dan tombol **QR HP** di topbar dashboard.
Gunakan URL HTTPS tunnel/hosting yang aktif atau IP LAN yang dapat dijangkau HP.
Jangan gunakan `localhost` sebagai alamat QR untuk perangkat lain. QR Web App
berbeda dari QR Akses Tamu.
