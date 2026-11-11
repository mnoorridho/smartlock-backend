# Catatan perubahan versi Smart Lock tanpa presensi

## Fitur aktif

- Login dan manajemen pengguna.
- Manajemen perangkat, status pintu/kunci, dan MQTT ke ESP32.
- Autentikasi NFC dan hasil verifikasi wajah dari client.
- Geotagging/geofence menggunakan jarak Haversine.
- Jam operasional global per perangkat, default 07:00–17:00 WIB.
- Pengecualian akses di luar jam untuk pengguna tertentu yang diaktifkan admin.
- Akses tamu melalui QR + PIN.
- Audit log percobaan akses.
- Dashboard web responsif dengan tampilan terang dan pengaturan jam pintu.

## Alur jam akses

1. Owner/admin mengatur jadwal di Dashboard > Perangkat > Jadwal Akses Pintu,
   atau memakai `PATCH /devices/{device_id}/access-schedule`.
2. Di luar jadwal, pengguna biasa ditolak pada unlock aplikasi, verifikasi wajah,
   verifikasi NFC berbasis hardware, serta akses tamu QR.
3. Untuk mengecualikan satu pengguna, admin mengaktifkan `allow_outside_schedule`
   pada permission pengguna. Izin ini tidak melewati validasi geofence.
4. Owner/admin dapat menjalankan unlock manual kapan saja.

## Modul akademik/presensi

Fitur periode akademik, mata kuliah, rombel, pengampu, jadwal kuliah, dan presensi
sudah dinonaktifkan dari dashboard dan API aktif. Router lama tidak lagi dibundel.
Tabel/model akademik yang mungkin sudah ada tetap dipertahankan agar migrasi tidak
menghapus data lama secara otomatis.

## Database

Migration baru `6f02a8b7c911_add_device_access_windows.py` menambahkan kolom jadwal
perangkat serta opsi izin akses di luar jam pada permission. Jalankan `alembic upgrade
head` sebelum menjalankan aplikasi pada database lama.
