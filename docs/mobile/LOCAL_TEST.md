# Backend uji lokal: desktop dan HP

Backend pengujian dijalankan pada port **8000**, berbeda dari preview UI 8766.
Database SQLite berada di `.local/smartlock-test.sqlite3`; kunci sesi lokal berada
di `.local/test-jwt-secret.txt`. Data akun dan pengaturan bertahan setelah restart.
`.env` dan PostgreSQL tidak diubah. MQTT dinonaktifkan dalam mode ini, sehingga
tidak ada perintah yang dapat membuka smartlock fisik. Simulator lokal kini memberi
heartbeat online pada perangkat virtual, menerima transaksi setelah validasi akses,
mengirim konfirmasi sukses sekitar 0,8 detik kemudian, dan mengunci kembali setelah
5 detik. Layar, respons API, dan audit membedakan hasil **SIMULASI** dari perangkat fisik.
Simulator hanya dapat diaktifkan oleh launcher ini terhadap file SQLite uji yang
ditentukan; backend PostgreSQL biasa tetap memakai MQTT dan ACK hardware.

## 1. Buka di desktop

1. Buka Chrome/Edge di komputer yang menjalankan backend.
2. Masuk ke **http://localhost:8000/dashboard** tanpa `?demo=1`.
3. Pilih **Daftar Akun**. Buat akun pertama dengan nama, email, dan password sendiri.
   Akun pertama pada database uji kosong otomatis menjadi **owner**.
4. Login memakai email/password tersebut. Tidak ada akun atau password bawaan.
5. Buat perangkat uji dari menu Perangkat. Pakai kode unik seperti `UJI-01`.
6. Buka jendela Incognito/InPrivate atau browser lain, lalu daftarkan akun kedua
   memakai email berbeda. Akun berikutnya menjadi **user**.
7. Dari akun owner, buka Permissions, pilih perangkat dan email user, lalu beri
   izin Wajah/NFC sesuai kebutuhan. Biarkan Akses Cepat tidak dicentang untuk
   mengecek tampilannya yang abu-abu.
8. Dari akun user, perbarui akses. Hanya perangkat yang diizinkan akan terlihat.

Email/password bisa digunakan langsung. Login Google memerlukan konfigurasi origin
OAuth dan email yang sudah terdaftar; konfigurasi Client ID saja belum menjamin
origin lokal maupun alamat tunnel sudah diizinkan. Cek README utama untuk OAuth.

Dokumentasi API: http://localhost:8000/docs.
Pemeriksaan server: http://localhost:8000/health.
Penanda mode uji: http://localhost:8000/local-test/info.

## 2. Buka di HP melalui Wi-Fi

1. Hubungkan HP dan komputer ke Wi-Fi yang sama. Komputer harus tetap menyala.
2. Alamat Wi-Fi komputer saat penyiapan adalah **192.168.1.6**.
3. Di Chrome/Safari HP, buka **http://192.168.1.6:8000/dashboard**.
   Jangan gunakan `localhost` di HP: itu menunjuk ke HP sendiri.
4. Login memakai akun owner/user yang baru Anda buat.
5. Pakai orientasi portrait dan nonaktifkan pilihan browser **Situs desktop**.
   Aplikasi memilih layout mobile otomatis; URL tetap sama.

Jika alamat berubah, jalankan `ipconfig` di komputer dan gunakan IPv4 adapter Wi-Fi.
Jika halaman gagal dimuat, buka dulu `/health` pada IP tersebut, pastikan backend
berjalan, dan periksa apakah Wi-Fi memakai isolasi klien/guest network.

Izin firewall belum berhasil ditambahkan otomatis karena Windows menolak hak
administratif. Jika koneksi HP diblokir, buka **PowerShell sebagai Administrator**
dan jalankan satu kali:

```powershell
New-NetFirewallRule -DisplayName 'Smartlock Local Test TCP 8000 (Wi-Fi)' -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8000 -RemoteAddress LocalSubnet -InterfaceAlias 'Wi-Fi' -Profile Any
```

Aturan dibatasi ke port 8000, adapter Wi-Fi, dan subnet lokal. Nama adapter dapat
disesuaikan dengan hasil `Get-NetAdapter`. Tidak perlu mematikan firewall Windows.

HTTP LAN cukup untuk memeriksa UI, daftar/login, perangkat, izin, kartu, dan riwayat.
**Kamera dan lokasi GPS di HP memerlukan HTTPS** untuk pemeriksaan wajah/geofence.

## 3. Menguji kamera/GPS HP melalui HTTPS

Ngrok kini sudah dipasang melalui Microsoft Store pada komputer ini. Untuk setup
authtoken lokal dan menjalankan tunnel secara otomatis, cukup jalankan:

```powershell
Set-Location 'E:\Downloads\smartlock-backend\smartlock-backend'
.\scripts\start_ngrok.ps1
```

Pada pemakaian pertama, salin authtoken dari
https://dashboard.ngrok.com/get-started/your-authtoken dan tempel pada prompt
tersembunyi. Jangan kirim token melalui chat. Script menyimpan konfigurasi di
`.local/ngrok.yml`, menjalankan agent di background, dan menampilkan URL HTTPS
lengkap `/dashboard`. URL juga tersimpan di `.local/ngrok-dashboard-url.txt`.
Perekaman request oleh inspector ngrok dinonaktifkan. Backend port 8000 harus
tetap berjalan. Jika script gagal, pesan agent berada di `.local/ngrok-agent.log`.
File konfigurasi mengandung token: jangan membagikannya.

Alternatif pemasangan/konfigurasi CLI manual:

1. Install ngrok dan masuk/daftar akun sesuai [panduan Windows resmi](https://ngrok.com/download/windows).
2. Pada terminal komputer, masukkan authtoken milik Anda secara lokal, lalu buat
   tunnel ke backend yang sudah berjalan:

```powershell
ngrok config add-authtoken "AUTHTOKEN_ANDA"
ngrok http 8000
```

3. Salin URL `https://...` yang muncul pada Forwarding, tambahkan `/dashboard`,
   lalu buka di browser HP. URL contoh bukan alamat yang sudah berjalan;
   gunakan URL yang diberikan ngrok. Tunnel membuat aplikasi uji tersedia lewat
   alamat publik selama proses ngrok berjalan; gunakan data pengujian.
4. Login lagi karena origin HTTPS memiliki penyimpanan sesi sendiri. Backend dan
   akun yang dipakai tetap database uji yang sama.
5. Izinkan akses kamera dan lokasi dari browser serta aktifkan lokasi di HP.
6. Owner perlu menyiapkan lokasi/radius dan izin wajah perangkat. User harus berada
   dalam radius dan jadwal yang diizinkan sebelum kamera Face Unlock dapat aktif.
7. Daftarkan wajah melalui tombol pendaftaran. Tekan **Ambil foto** ketika siap;
   tidak ada pemindaian otomatis pada pendaftaran. Periksa foto di bingkai, lalu tekan
   **Gunakan foto ini** atau **Ambil ulang**. Setelah tersimpan, coba **Buka dengan wajah**.
   GPS, radius, izin, kualitas dan identitas tetap diperiksa. Setelah ACK virtual,
   muncul **Smartlock berhasil dibuka — Simulasi** beserta nama akun yang wajahnya
   cocok. Tidak ada unlock fisik. Face Unlock juga memakai tombol **Ambil foto**,
   tanpa pemindaian otomatis; foto yang tidak layak perlu diambil ulang.
8. Owner dapat memilih **Pengaturan → Threshold Face Unlock per user**, memilih
   perangkat/user dan menyimpan nilai 0.30–0.55 (default 0.45). Nilai lebih rendah
   lebih ketat. Setiap jepretan diperiksa satu kali. Pemuatan model pertama dan
   pengambilan GPS tetap dapat membutuhkan waktu tambahan.

Lihat persyaratan browser untuk [kamera](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia)
dan [geolokasi](https://developer.mozilla.org/en-US/docs/Web/API/Geolocation_API).

## 4. Menjalankan lagi setelah backend berhenti

Dari PowerShell biasa, jalankan:

```powershell
Set-Location 'E:\Downloads\smartlock-backend\smartlock-backend'
.\scripts\start_backend.ps1 -LocalTest
```

Script memakai `.venv` jika tersedia, atau Python 3.12 bawaan Codex beserta
dependensi proyek yang sudah tersedia pada komputer ini. Jangan jalankan salinan
kedua ketika port 8000 masih dipakai. Terminal yang menjalankan server harus tetap
terbuka; tekan Ctrl+C pada terminal tersebut untuk menghentikannya.

Jika PowerShell membatasi script, gunakan perintah langsung berikut pada komputer ini:

```powershell
Set-Location 'E:\Downloads\smartlock-backend\smartlock-backend'
$env:PYTHONPATH="$PWD;$PWD\venv\Lib\site-packages"
& "$env:USERPROFILE\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" scripts/run_local_backend.py --host 0.0.0.0 --port 8000
```

Mode PostgreSQL asli menggunakan `start_backend.ps1` tanpa `-LocalTest`, setelah
password DATABASE_URL benar dan migrasi ditinjau/dijalankan. Saat penyiapan ini,
PostgreSQL menolak password dari `.env`, sehingga mode asli belum siap untuk login.

## Verifikasi yang sudah dilakukan

- HTTP 200 untuk `/health` dan `/dashboard` lewat localhost dan alamat Wi-Fi komputer.
- Daftar/login lewat HTTP sungguhan, role pertama owner dan berikutnya user.
- User hanya melihat perangkat yang diberi izin dan quick access tetap tidak diizinkan.
- Akun dan perangkat sementara dari pemeriksaan dibersihkan. Database siap untuk
  pendaftaran akun Anda sendiri. Tidak ada perintah unlock yang dikirim.
- Koneksi dari perangkat HP lain, autentikasi Google, HTTPS tunnel, dan smartlock
  fisik belum diuji langsung pada penyiapan ini.
