# Batas fitur owner dan user

Pratinjau user: `http://127.0.0.1:8766/dashboard?demo=1&role=user`.
Tombol **Coba tampilan user** juga tersedia di layar login. Demo tidak menyimpan
referensi/kartu dan tidak mengirim perintah ke perangkat fisik.

## Susunan UI/UX user

- Beranda mengikuti pola owner: ringkasan perangkat/metode/kartu, perangkat utama,
  panel izin, pendaftaran identitas, aktivitas terbaru, dan kartu perangkat.
- Perangkat Saya menggunakan daftar pilihan dan detail perangkat yang hanya dapat
  dibaca, dengan metode buka sesuai izin owner. Tombol Perbarui akses memuat kembali
  status dan hak akses dari server.
- NFC menampilkan ringkasan, form pendaftaran dengan validasi, panduan, serta kartu
  aktif/nonaktif milik sendiri. Tidak ada aksi menghapus atau mengatur kartu orang lain.
- Riwayat menampilkan ringkasan catatan yang dimuat, filter metode/hasil, dan timeline
  pribadi. Angka ringkasan berasal dari catatan yang ditampilkan, bukan klaim total
  seluruh riwayat pengguna.
- Profil menampilkan identitas akun, ruang akses, dan status pendaftaran wajah/NFC.
  Status wajah dibaca melalui `/auth/me/face-profile/status`, tanpa mengunduh descriptor
  biometrik hanya untuk menampilkan badge. Pendaftaran yang berhasil memperbarui badge.

Setiap bagian memiliki status memuat, kosong, atau gagal dimuat. Data async dari
perangkat/akun lama tidak menimpa halaman yang baru dipilih. User tetap tidak memperoleh
kontrol pengelolaan owner. Demo menyediakan contoh kartu dan aktivitas berlabel simulasi.

## User

User hanya mendapat tampilan berikut:

- Perangkat yang disetujui owner, dengan nama owner dan pilihan perangkat.
- Metode wajah, NFC, dan quick access sesuai izin per user/perangkat. Metode yang
  belum diizinkan tampil abu-abu dan nonaktif, dengan penjelasan dari owner.
- Daftar wajah akun sendiri, setelah memiliki izin wajah pada perangkat aktif.
- Daftar dan lihat kartu NFC akun sendiri pada perangkat yang mengizinkan NFC.
- Riwayat akses sendiri untuk perangkat yang masih boleh diakses.
- Identitas akun dan tombol keluar. Tidak ada pengaturan/manajemen perangkat.

Pendaftaran tidak membuat hak akses baru. User tidak dapat memilih akun lain,
mengubah owner, mengaktifkan metode, mengubah jadwal/radius, memberi izin kepada
orang lain, mengelola kartu orang lain, atau membuat akses tamu. API tetap menolak
operasi tersebut meskipun pengguna memanipulasi tombol atau mengirim request manual.
Kartu user terikat otomatis ke ID akun dari token login. Referensi wajah self-service
selalu disimpan ke ID akun yang sedang login, bukan ID dari body request.

## Owner

Owner tetap mengatur perangkat miliknya, lokasi/radius, metode aktif di perangkat,
jadwal, pengguna yang disetujui, kartu, dan akses tamu. Di **Permissions**, owner
dapat mencentang metode **Wajah**, **NFC**, dan **Quick** saat memberikan atau
memperbarui izin. Tidak ada perubahan hak akses yang dapat dilakukan oleh user.

Migrasi mempertahankan hak wajah/NFC pada izin lama (`true`) dan menolak quick
secara default (`false`). Metode wajah/NFC juga harus aktif pada konfigurasi
perangkat; izin personal saja tidak dapat menyalakannya.

## Urutan Face Unlock user

1. Cek sesi, perangkat yang disetujui, izin metode wajah, dan jadwal di server.
2. Ambil GPS terbaru lalu panggil `POST /devices/{id}/face-precheck`.
3. Jika koordinat belum diatur owner, akurasi buruk, atau di luar radius: tampilkan
   alasan dan jangan mengaktifkan kamera.
4. Jika lolos radius: muat referensi identitas dan aktifkan preview kamera. User
   menekan Ambil foto; satu foto diperiksa geometri/resolusinya dan dicocokkan
   dengan referensi seperti panduan Face Unlock. Tidak ada loop pemindaian.
5. Setelah wajah cocok, ambil lokasi baru lagi. Endpoint unlock memeriksa ulang
   izin, jadwal, metode, akurasi GPS, dan radius sebelum menerbitkan perintah MQTT.
6. Pantau konfirmasi transaksi. `command_sent` belum berarti perangkat berhasil
   menjalankan perintah. Riwayat user tidak menampilkan aktivitas pengguna lain.

NFC tetap mengikuti rancangan prototype: UID kartu harus terdaftar pada perangkat,
aktif, terikat ke akun user yang benar, dan metode NFC harus diizinkan owner. Form
UID tidak menjamin dukungan scan NFC otomatis pada seluruh browser. Pengguna
memasukkan UID yang dibaca dari kartu/reader. Untuk penggunaan fisik, reader ESP32
memvalidasi kartu melalui endpoint hardware yang juga memeriksa izin metode.

## Endpoint dan batasnya

| Endpoint | User | Owner |
|---|---|---|
| `GET /devices/`, `GET /devices/{id}` | Hanya perangkat disetujui | Hanya perangkat miliknya |
| `PUT /auth/me/face-profile` | Akun sendiri, perlu izin wajah aktif | Akun sendiri |
| `PUT /auth/users/{id}/face-profile` | Ditolak | Pendaftaran melalui pengelolaan owner |
| `POST /nfc-cards/` | Diri sendiri, perlu izin NFC | Pengelolaan kartu perangkat miliknya |
| `GET /nfc-cards/` | Hanya kartu sendiri pada perangkat diizinkan | Kartu perangkat miliknya |
| `PATCH/DELETE /nfc-cards/{id}` | Ditolak | Perangkat miliknya |
| `POST /devices/{id}/face-precheck` | Izin wajah + jadwal + GPS/radius | Perangkat miliknya |
| `POST /devices/{id}/quick-unlock` | Hanya jika owner memberi `allow_quick` | Perangkat miliknya |
| `GET /devices/{id}/logs` | Riwayat sendiri | Riwayat perangkat miliknya |
| Manajemen device, permission, guest | Ditolak | Sesuai kepemilikan perangkat |

Quick access tidak tersedia sebagai bypass umum: endpoint memeriksa izin metode
di server. Kartu owner lama tetap memakai tombol Face Unlock dan Daftarkan wajah;
pilihan quick ditampilkan pada portal user dengan status sesuai hak dari owner.

## Migrasi dan menjalankan

Dengan environment backend aktif, dari root proyek:

```powershell
python -m alembic current
python -m alembic upgrade head
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Revisi baru `e18b6a2d0419` menambahkan `allow_face`, `allow_nfc`, dan `allow_quick`
ke tabel permissions. Migrasi ini diuji pada SQLite terisolasi dan belum diterapkan
ke database PostgreSQL pengguna. Periksa panduan migrasi utama bila database Anda
masih berada sebelum revisi lama yang menghapus fitur akademik.

## Pengujian dan batas

- `scripts/check_user_roles.py`: matriks API user/owner, metode diizinkan/dicabut,
  pemisahan perangkat/riwayat/kartu, pendaftaran akun sendiri, geofence, hardware,
  dan migrasi tambahan tanpa mengubah data izin lama. Menggunakan SQLite dan MQTT mock.
- `scripts/check_face_browser.cjs`: kamera sintetis, geofence menolak sebelum
  kamera, pendaftaran wajah user sendiri, form NFC sendiri, dan menu owner dibatasi.
- `scripts/check_mobile_dashboard.cjs`: regresi desktop/mobile dan layout user.
- `scripts/check_user_portal.cjs`: seluruh halaman user pada desktop, mobile/320 px,
  kedua tema, filter riwayat, validasi NFC, status gagal dimuat, dan batas menu owner.

GPS, kamera wajah nyata, kartu/reader fisik, dan ESP32 belum diuji end-to-end.
Pencocokan wajah dan UID NFC masih mengikuti kontrak client-trust prototype.
Lihat batas akurasi/anti-spoof pada [panduan Face Unlock](FACE_UNLOCK.md).
