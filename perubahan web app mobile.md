# Perubahan Web App Mobile Smartlock

Dokumentasi perubahan sampai **31 Oktober 2026**.

File ini merangkum perubahan tampilan, autentikasi, hak akses, Face Unlock, dan
lingkungan pengujian yang dibuat selama pengembangan.

## 1. Lokasi proyek

Folder utama yang Anda buka:

```text
E:\Downloads\smartlock-backend
```

Kode aplikasi berada di subfolder:

```text
E:\Downloads\smartlock-backend\smartlock-backend
```

Perintah menjalankan aplikasi harus dilakukan dari subfolder yang berisi `app`,
`scripts`, `requirements.txt`, dan `.env` tersebut.

## 2. Tampilan desktop dan mobile

- Tampilan desktop dipertahankan. Versi mobile menggunakan identitas warna,
  tipografi, ikon, serta komponen dashboard yang sama.
- Deteksi layout menggunakan media query sampai 768 piksel, viewport, dan
  informasi perangkat. URL halaman tetap `/dashboard`.
- Navigasi utama mobile berada di bagian bawah; menu tambahan menggunakan drawer.
- Halaman mobile selain Beranda memiliki tombol ringkas **← Beranda**. Tombol
  tidak lagi berbentuk kotak panjang selebar layar.
- Kartu ringkasan mobile disusun menjadi **grid dua kolom tanpa geser horizontal**.
  Ringkasan NFC/riwayat disusun vertikal. Daftar perangkat tertentu tetap dapat
  digeser ke samping.
- Tombol dan kontrol mobile memiliki area sentuh minimal 44 × 44 piksel.
- Layout memperhitungkan safe area serta ruang untuk navigasi bawah.
- HP yang diputar ke landscape menampilkan overlay instruksi kembali ke portrait.
  Screen Orientation API dicoba jika browser mendukung; overlay menjadi fallback.

## 3. Tema terang dan gelap

- Pemilih tema tersedia pada halaman login serta header owner dan user.
- Halaman pendaftaran dan layar wajah mengikuti pilihan tema.
- Pilihan tema disimpan di browser dan dipulihkan setelah halaman dimuat ulang.
- Mengganti tema tidak menghapus isian form.

## 4. Form masuk dan pendaftaran

### Teks isian dan tombol mata

| Bagian | Petunjuk isian |
| --- | --- |
| Email masuk | Masukkan email Anda |
| Password masuk | Masukkan Password Anda |
| Nama pendaftaran | Masukkan nama Anda |
| Email pendaftaran | Masukkan email Anda |
| Password pendaftaran | Minimal 6 karakter |

Kolom password masuk dan daftar memiliki tombol mata untuk menampilkan atau
menyembunyikan password. Tombol menggunakan label aksesibilitas yang mengikuti
kondisinya. Password disembunyikan lagi saat berganti tab autentikasi atau logout.

### Aturan password wajib saat daftar

Password akun baru harus memenuhi seluruh syarat:

1. Minimal **6 karakter**.
2. Minimal **1 huruf besar A–Z**.
3. Minimal **1 huruf kecil a–z**.
4. Minimal **1 angka 0–9**.

Pemeriksaan dilakukan pada form **dan backend**, sehingga tidak dapat dilewati
hanya dengan mengirim permintaan API langsung. Pesan menyebutkan syarat yang kurang,
misalnya:

> Password belum memenuhi syarat: 1 huruf besar (A–Z), 1 angka (0–9).

Pesan kesalahan muncul pada halaman dan di dekat kolom password. Setelah isian
diperbaiki, pesan pada kolom diperbarui. Respons validasi pendaftaran tidak
mengembalikan isi password yang ditolak. Aturan baru ini diterapkan pada
pendaftaran; password akun lama tidak diubah.

### Login dan penghapusan demo

- Tombol masuk demo, fungsi masuk tanpa akun, serta data dummy bawaan frontend
  sudah dihapus.
- Parameter `?demo=1` tidak lagi membuka dashboard tanpa autentikasi.
- Server preview demo lama pada port 8766 dihentikan. Gunakan backend port 8000.
- Akun pengujian dan perangkat virtual yang disimpan di backend tetap tersedia;
  keduanya berbeda dari data dummy frontend yang dihapus.
- Pembacaan `.env` diperbaiki agar menggunakan lokasi proyek, bukan bergantung
  pada folder kerja terminal.
- Login Google memerlukan Client ID, origin OAuth yang sesuai, dan akun Smartlock
  dengan email yang sama. Login Google belum diverifikasi langsung pada pengujian ini.

## 5. Perbedaan owner dan user

Portal user menggunakan pola UI dashboard owner, dengan fitur sesuai perannya.

| Fitur | Owner | User |
| --- | --- | --- |
| Pengaturan perangkat, lokasi/radius, jadwal | Kelola perangkat miliknya | Tidak tersedia |
| Pemberian/pencabutan izin | Kelola perangkat miliknya | Tidak tersedia |
| Pemilihan perangkat | Perangkat miliknya | Hanya yang diberi izin owner |
| Daftar wajah | Akun sendiri dan pendaftaran melalui pemilih akun | Akun sendiri jika diizinkan |
| Daftar kartu NFC | Pengelolaan sesuai hak owner | Kartu sendiri pada perangkat yang diizinkan |
| Riwayat | Perangkat miliknya | Hanya aktivitas akun sendiri pada perangkat yang diizinkan |
| Tema tampilan | Tersedia | Tersedia |

Halaman user meliputi **Beranda, Perangkat, NFC, Riwayat, dan Profil**. Bagian-bagian
tersebut dilengkapi ringkasan, detail perangkat/owner, status pendaftaran, panduan,
filter riwayat, serta kondisi kosong dan gagal memuat.

Hak akses metode diberikan per user dan perangkat:

- `allow_face`: membuka melalui wajah.
- `allow_nfc`: menggunakan kartu NFC.
- `allow_quick`: membuka melalui akses cepat.

Metode yang tidak diizinkan ditampilkan abu-abu dan tidak dapat ditekan. Backend
juga memeriksa izin; pembatasan tidak hanya berupa tampilan tombol. Quick Access
secara default tidak diberikan. Pada kartu utama owner, tombol bawah yang
sebelumnya Akses Cepat diganti menjadi **Daftarkan wajah**.

Pendaftaran NFC melalui web saat ini memakai UID yang dimasukkan pengguna;
bukan pembacaan kartu otomatis pada semua browser HP.

## 6. Pendaftaran wajah dan Face Unlock — versi terbaru

### Menggunakan foto manual

Kedua alur kini memakai **satu jepretan foto**, bukan pemindaian video berulang.

**Pendaftaran:**

1. Buka Daftar wajah dan setujui pendaftaran.
2. Kamera depan ditampilkan dalam bingkai oval.
3. Tekan **Ambil foto** saat siap.
4. Kamera berhenti dan hasil jepretan ditampilkan di dalam bingkai.
5. Foto diperiksa. Pilih **Gunakan foto ini** untuk menyimpan referensi, atau
   **Ambil ulang** untuk mengambil foto baru.

**Face Unlock:**

1. Periksa izin, jadwal, GPS, akurasi, dan radius sebelum kamera diaktifkan.
2. Tampilkan akun yang akan dicocokkan dan batas pencocokan yang berlaku.
3. Pengguna menekan **Ambil foto**; kamera langsung dihentikan.
4. Periksa jumlah wajah, geometri/resolusi, dan cocokkan foto dengan referensi
   akun yang sedang login.
5. Ambil GPS baru serta baca ulang referensi dan kebijakan sebelum mengirim
   satu permintaan unlock.
6. Tunggu konfirmasi transaksi perangkat. Setelah berhasil, tampilkan nama akun
   yang wajahnya cocok dan notifikasi hasil buka kunci.

Instruksi meminta pengguna berada di tempat terang, menghadap kamera, dan
memastikan mata, hidung, serta mulut terlihat jelas. Tidak ada deteksi otomatis
sebelum tombol foto ditekan dan tidak ada titik progres pemindaian pada versi ini.

Foto hanya digunakan sementara selama proses di halaman. Server menyimpan
descriptor numerik, bukan foto/video. Pendaftaran baru memakai satu descriptor;
referensi lama berisi tiga descriptor tetap didukung.

### Koreksi filter kualitas dan pesan penolakan

- Pemeriksaan awal pernah terlalu ketat terhadap posisi, seluruh landmark,
  keyakinan detektor, serta tekstur piksel bagian wajah.
- Versi terbaru memakai pedoman input foto minimal **480 × 360 piksel** dan
  wajah minimal **100 × 100 piksel**, pemeriksaan landmark utama, dan keyakinan
  detektor yang dipisahkan dari threshold identitas.
- Kontras hidung/mulut, rasio mata, ketajaman piksel, dan perkiraan yaw/pitch yang
  belum dikalibrasi tidak lagi menjadi penolak otomatis. Nilainya dapat dicatat
  sebagai metadata diagnostik.
- Pesan membedakan kualitas foto, pencocokan identitas, izin, dan GPS. Penolakan
  identitas menampilkan jarak pencocokan serta threshold yang berlaku.
- Aset wajah diberi versi dan header tanpa cache agar perbaikan terbaru diterima
  setelah halaman dimuat ulang.

### Threshold owner

Owner membuka **Pengaturan → Threshold Face Unlock per user**, memilih perangkat
dan user, lalu menyimpan nilai:

| Nilai | Arti pada engine saat ini |
| --- | --- |
| 0.30 | Sangat ketat |
| 0.45 | Default |
| 0.55 | Lebih toleran |

Nilai adalah batas jarak pencocokan, bukan persentase keyakinan. **Makin kecil
nilainya, makin ketat pencocokan.** Pengaturan user tidak mengubah default 0.45
ketika pemilik perangkat membuka sebagai owner. Threshold tidak melewati
pemeriksaan GPS atau izin akses.

### Status ML Kit / MobileFaceNet

Engine yang terpasang masih **FaceAPI 1.7.15 dengan descriptor 128 dimensi**.
Pedoman ukuran input Google dipakai sebagai acuan pemeriksaan gambar. Aplikasi
belum dipindahkan ke ML Kit native atau MobileFaceNet dan tidak mengklaim
sertifikasi kedua teknologi tersebut.

ML Kit Face Detection mendeteksi wajah/landmark, bukan identitas. MobileFaceNet
adalah model embedding berbeda; penggantian memerlukan model terlatih, alignment
dan normalisasi yang sesuai, referensi baru, serta kalibrasi threshold. Descriptor
FaceAPI tidak dapat langsung dibandingkan dengan descriptor MobileFaceNet.

### Diagnostik dan batas pengujian wajah

`POST /auth/me/face-diagnostics` mencatat metadata tahap pemeriksaan, versi client,
ukuran gambar/wajah, skor detektor, alasan, dan jarak/threshold jika tersedia.
`GET` pada alamat yang sama hanya membaca hasil akun sendiri.

Penyimpanan dibatasi maksimal 10 hasil per akun dan 128 akun di memori proses;
hilang saat backend direstart. Endpoint menolak foto, descriptor, koordinat GPS,
field tambahan, dan angka non-finite.

Pengujian sintetis dan API sudah dilakukan, tetapi **penyebab pasti penolakan
pada HP pengguna belum terkonfirmasi melalui percobaan diagnostik terbaru**.
Keberhasilan mengenali wajah nyata di HP tidak boleh dianggap sudah terbukti
hanya dari tes kamera sintetis. Sistem juga belum memiliki liveness/anti-spoof
tersertifikasi; hasil wajah prototipe masih diproses di client.

## 7. Backend uji, simulator, dan HTTPS

### Database uji

- Backend FastAPI dijalankan pada port **8000**.
- PostgreSQL lokal terdeteksi aktif, tetapi password `DATABASE_URL` ditolak pada
  penyiapan sebelumnya. Konfigurasi PostgreSQL belum diperbaiki dalam pekerjaan ini.
- Sesuai pilihan pengguna, tersedia SQLite terpisah di
  `smartlock-backend\.local\smartlock-test.sqlite3`.
- `.env` dan isi database PostgreSQL tidak diubah untuk menjalankan mode uji.
- Kunci sesi lokal tersimpan terpisah sehingga sesi dapat dipakai lagi setelah
  restart selama token masih berlaku.

### Perangkat virtual

Simulator hanya dapat diaktifkan melalui launcher SQLite uji yang ditentukan.
MQTT fisik dinonaktifkan dalam mode tersebut.

Simulator memberi heartbeat online, mengonfirmasi transaksi sekitar 0,8 detik
setelah diterima, lalu mengunci kembali sekitar 5 detik kemudian. Hasil layar,
API, dan riwayat diberi label **SIMULASI**. Validasi GPS, izin, dan identitas tetap
dijalankan. Tidak ada pintu fisik yang dibuka.

Akun owner/user dan perangkat uji pernah dibuat. Informasi lokalnya tersedia di
`smartlock-backend\.local\phone-test-accounts.json`; password tidak disalin ke
README ini.

### Menjalankan backend

```powershell
Set-Location 'E:\Downloads\smartlock-backend\smartlock-backend'
.\scripts\start_backend.ps1 -LocalTest
```

Jangan menjalankan proses kedua jika port 8000 masih digunakan. Script memilih
`.venv` jika tersedia atau Python/dependensi lokal yang sudah disiapkan pada
komputer ini. Environment `venv` lama merujuk Python komputer asal sehingga tidak
dipakai langsung sebagai executable.

Desktop: **http://localhost:8000/dashboard**.

HP satu Wi-Fi dapat memakai IP LAN komputer, misalnya alamat saat penyiapan
**http://192.168.1.6:8000/dashboard**. IP dapat berubah; cek dengan `ipconfig`.
HTTP LAN cukup untuk UI/login, sedangkan kamera/GPS HP memerlukan HTTPS.

### Menjalankan HTTPS ngrok

Ngrok dipasang melalui Microsoft Store setelah ZIP resmi diblokir Windows Defender.

```powershell
Set-Location 'E:\Downloads\smartlock-backend\smartlock-backend'
.\scripts\start_ngrok.ps1
```

Script meminta authtoken secara tersembunyi jika konfigurasi belum ada, lalu
menampilkan URL HTTPS dengan `/dashboard`. URL terakhir disimpan di
`smartlock-backend\.local\ngrok-dashboard-url.txt`. Authtoken tidak dicantumkan
di README ini.

Alamat yang dipakai selama pengujian:

https://nebulizer-autism-throwaway.ngrok-free.dev/dashboard

Alamat hanya dapat dipakai selama tunnel dan backend berjalan. Komputer harus
tetap menyala. Buka melalui Chrome/Safari HP, izinkan kamera dan lokasi, serta
gunakan portrait. Pengaturan Google OAuth untuk origin ngrok masih perlu
disesuaikan jika ingin memakai login Google.

Izin firewall LAN tidak berhasil ditambahkan otomatis karena membutuhkan hak
Administrator. Langkah firewall tersedia di panduan `LOCAL_TEST.md` di bawah;
tidak perlu mematikan firewall Windows.

## 8. File utama dan migrasi

Semua lokasi berikut relatif terhadap folder kode
`E:\Downloads\smartlock-backend\smartlock-backend`.

| File/folder | Perubahan utama |
| --- | --- |
| `app/static_pages/dashboard.html` | Layout, navigasi, tema, form/password, role, pengaturan threshold, penghapusan demo |
| `app/static_pages/user-portal.js` dan `.css` | Halaman dan komponen khusus user |
| `app/static_pages/face-unlock.js` | Kamera, foto manual, GPS, referensi, pencocokan, transaksi dan diagnostik |
| `app/static_pages/face-unlock-core.js` | Validasi foto, descriptor dan jarak pencocokan |
| `app/static_pages/face-unlock.css` | Bingkai oval, foto, tema dan kontrol kamera |
| `app/device_access.py` | Pemeriksaan perangkat dan izin metode bersama |
| `app/models.py`, `app/schemas.py` | Referensi wajah, izin metode, threshold, validasi data dan password |
| `app/routers/` | Pembatasan role, endpoint wajah/izin/NFC/perangkat, aset dashboard |
| `app/face_diagnostics.py` | Diagnostik metadata terbatas per akun |
| `app/local_simulator.py` | Heartbeat dan ACK virtual khusus mode uji |
| `app/config.py`, `app/main.py` | Lokasi `.env` dan pesan validasi pendaftaran |
| `scripts/start_backend.ps1`, `scripts/run_local_backend.py` | Launcher backend biasa dan SQLite uji |
| `scripts/start_ngrok.ps1` | Setup lokal dan tunnel HTTPS |

Migrasi tambahan yang disiapkan:

- `c4d91e830af2`: tabel referensi wajah.
- `e18b6a2d0419`: izin wajah, NFC, dan Quick Access.
- `f6b319e048c2`: threshold pencocokan per izin user/perangkat.

Migrasi produksi PostgreSQL belum diterapkan oleh pekerjaan ini. Tinjau riwayat
migrasi sebelum `alembic upgrade head`, karena ada migrasi lama di proyek yang
menghapus tabel akademik. Launcher SQLite uji menambahkan kolom threshold secara
aditif pada database ujinya sendiri.

## 9. Pemeriksaan yang telah dilakukan

- Layout desktop dan mobile sampai lebar 320 piksel, kedua tema, navigasi,
  area sentuh, drawer, tabel, dan overlay portrait.
- Pembatasan owner/user, izin metode, perangkat yang disetujui, dan privasi riwayat.
- Foto manual, ambil ulang, konfirmasi pendaftaran, penghentian kamera, pembatalan,
  foto tidak cocok, serta penolakan GPS melalui kamera/model sintetis.
- Pendaftaran/login melalui HTTP pada database uji dan API dengan SQLite in-memory.
- Threshold owner, simulator online, konfirmasi transaksi, audit dan penguncian ulang.
- Password wajib: setiap syarat yang kurang, pengiriman API langsung, password
  valid, tampilan pesan, dan respons tanpa mengembalikan password.

Script pemeriksaan meliputi `check_face_core.cjs`, `check_face_browser.cjs`,
`check_face_backend.py`, `check_user_roles.py`, `check_registration_password.py`,
`check_simulator_threshold.py`, `check_threshold_settings.cjs`,
`check_mobile_dashboard.cjs`, dan `check_appearance_navigation.cjs`.

Fixture kamera/model/data di dalam script pengujian terpisah dari aplikasi yang
disajikan ke pengguna; bukan data dummy frontend yang dimuat saat login.

## 10. Panduan lanjutan

- [Menjalankan backend uji, desktop/HP, firewall dan ngrok](smartlock-backend/docs/mobile/LOCAL_TEST.md)
- [Alur wajah, diagnostik dan batas akurasi](smartlock-backend/docs/mobile/FACE_UNLOCK.md)
- [Portal user dan batas hak akses](smartlock-backend/docs/mobile/USER_ROLES.md)
- [README dashboard mobile](smartlock-backend/docs/mobile/README.md)
- [README proyek/backend](smartlock-backend/README.md)


## Pembaruan 2 November 2026 — QR Web App dan responsivitas

- Layout HP tetap portrait; jika perangkat HP diputar ke landscape, overlay
  meminta pengguna kembali ke portrait.
- Layout laptop/PC tetap desktop lebar (landscape), termasuk laptop layar sentuh
  dengan viewport lebar.
- QR Web App ditambahkan pada panel halaman login desktop dan tombol **QR HP**
  di topbar dashboard desktop.
- QR dibuat dinamis dari origin aktif ditambah `/dashboard`; URL ngrok lama
  tidak disimpan di kode. Gunakan alamat HTTPS tunnel/hosting aktif atau IP LAN
  yang dapat dijangkau HP. Kamera dan GPS browser HP memerlukan HTTPS.
- QR Web App terpisah dari QR Akses Tamu (`/guest/{token}`).
- Pemeriksaan layout diperluas untuk memastikan QR desktop tidak muncul pada
  layout HP dan tombol QR membuka tautan Web App yang tepat.
