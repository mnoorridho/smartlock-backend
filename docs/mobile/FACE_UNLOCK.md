# Face Unlock dan Pendaftaran Wajah

Panduan ini menjelaskan engine Face Unlock. Untuk portal user, izin metode dari
owner, dan pendaftaran akun sendiri, lihat [batas peran](USER_ROLES.md). Kamera
sekarang baru aktif setelah pemeriksaan lokasi/radius di server lolos.

Kartu perangkat pilihan memiliki dua tombol: **Unlock dengan verifikasi wajah**
di atas dan **Daftarkan wajah** di bawah. Pada HP, tombol mengikuti susunan vertikal.
Layar Face Unlock mengikuti tema terang/gelap dashboard, dengan kamera depan
bermasker oval, tombol kembali, instruksi dinamis, outline biru/oranye/hijau/merah,
tanpa titik progres pemindaian.

## Menjalankan dengan akun asli

1. Siapkan backend dan database sesuai README utama. Pastikan revisi database saat
   ini sudah `b7e26c4d91a0`. Tinjau riwayat migrasi sebelum memperbarui database lama:
   beberapa migrasi sebelumnya menghapus tabel akademik yang sudah dihentikan.
2. Terapkan migrasi baru dengan `python -m alembic upgrade head` dari environment
   proyek. Migrasi `c4d91e830af2` hanya menambahkan tabel `face_profiles` dan tidak
   mengubah akun/perangkat yang sudah ada. Migrasi ini belum diterapkan ke database
   PostgreSQL pengguna oleh Codex.
3. Restart backend. Buka `/dashboard` melalui HTTPS, atau localhost pada komputer
   yang sama. Akses IP LAN melalui HTTP tidak cukup untuk kamera/GPS di HP.
4. Masuk sebagai owner. Buka **Pengaturan → Referensi Face Unlock**, pilih akun
   pemilik wajah, lalu **Daftarkan / perbarui wajah**. Pastikan identitas pemilik
   akun dan persetujuannya sebelum pendaftaran. Kamera menampilkan pratinjau tanpa
   pemindaian otomatis. Tekan **Ambil foto**, periksa hasilnya lalu **Gunakan foto ini**.
   Pendaftaran wajah tidak mengubah izin perangkat atau
   mengaktifkan verifikasi wajah pada perangkat secara otomatis.
5. Aktifkan Verifikasi Wajah pada pengaturan perangkat jika diperlukan. Masuk dengan
   akun yang sudah didaftarkan, pilih perangkat, lalu **Unlock dengan verifikasi
   wajah**. Berikan izin kamera depan dan GPS.

User yang telah diizinkan owner juga dapat mendaftarkan wajah akun sendiri melalui
tombol Daftar wajah pada portal user; tidak dapat mendaftarkan akun orang lain.
Pendaftaran baru menyimpan satu descriptor 128 dimensi dari satu foto yang diambil
manual; profil lama dengan tiga descriptor tetap didukung tanpa pendaftaran ulang.
Foto/video tidak dikirim atau disimpan. Descriptor diproses di browser lalu disimpan
di database melalui endpoint owner atau endpoint akun sendiri yang sudah diizinkan;
data ini tetap merupakan data biometrik dan
perlu dilindungi dalam pengoperasian serta backup database. Referensi hanya dapat
dibaca oleh akun bersangkutan, diberi `Cache-Control: no-store`, dan tidak disimpan
di localStorage. Owner dapat mencabutnya dengan tombol **Hapus referensi**.

## Alur foto untuk pendaftaran dan unlock

Tidak ada pemindaian frame berulang, penghitungan stabilitas, atau titik progres.
Kamera hanya menampilkan preview hingga tombol **Ambil foto** ditekan. Arahan di
layar meminta tempat terang dan wajah menghadap kamera dengan mata/hidung/mulut jelas.

1. Untuk unlock, GPS baru dan `/devices/{id}/face-precheck` harus lolos sebelum kamera
   aktif. Server memeriksa izin, jam, akurasi, radius, dan mengirim threshold owner.
2. User menekan **Ambil foto**. Satu snapshot dibekukan di dalam oval dan kamera
   langsung dihentikan; tidak ada deteksi otomatis sebelum tombol ditekan.
3. Satu foto diperiksa jumlah wajah, posisi, landmark, pencahayaan, ketajaman dan
   descriptor. Foto tanpa wajah, lebih dari satu wajah atau kualitas buruk tidak
   dapat dipakai. User dapat memilih **Ambil ulang**.
4. Pendaftaran menyimpan satu descriptor hanya setelah **Gunakan foto ini**.
   Profil lama berisi tiga descriptor tetap didukung.
5. Unlock membandingkan descriptor foto dengan referensi akun sendiri. Ambil GPS baru
   lagi, baca ulang referensi dan kebijakan/threshold sebelum mengirim satu perintah.
   GPS, izin dan threshold tidak dilewati karena memakai foto.
6. Setelah ACK transaksi sukses, tampil nama profil yang cocok dan hasil unlock;
   smartlock virtual selalu berlabel **Simulasi**. Keluar/landscape membatalkan
   pemeriksaan foto yang masih berlangsung. Foto dibersihkan saat layar ditutup.

Owner mengatur threshold di **Pengaturan → Threshold Face Unlock per user**.
Default 0.45, rentang 0.30–0.55; lebih kecil lebih ketat. Foto tunggal memerlukan satu
kecocokan; profil lama minimal dua dari tiga referensi. Threshold bukan persentase.

Jika foto ditolak, pesan **Kualitas foto** berarti pencocokan belum dijalankan;
mengubah threshold identitas tidak mengubah hasil pemeriksaan kualitas. Deteksi
menggunakan input 512 dan filter keyakinan minimal 0.50. Foto minimal 480 × 360
dan wajah minimal 100 × 100 piksel mengikuti [pedoman input ML Kit](https://developers.google.com/ml-kit/vision/face-detection/android).
Landmark utama mata/hidung/mulut harus berada dalam gambar. Nilai kontras bagian
kulit, ketajaman piksel 64 × 64, EAR mata, dan perkiraan yaw/pitch manual tidak lagi
menjadi penolak otomatis: angka tersebut tidak dikalibrasi sebagai model oklusi.
Nilainya hanya dikirim sebagai metadata diagnostik. Pemeriksaan ini bukan model
khusus deteksi masker atau liveness.
Pesan kegagalan pencocokan menampilkan jarak keputusan dan threshold yang berlaku.
0.30 sangat ketat, 0.45 default, 0.55 lebih toleran. Pengaturan user tidak mengubah
threshold default 0.45 untuk pemilik perangkat yang melakukan unlock sebagai owner.

### Status ML Kit / MobileFaceNet dan diagnostik

- Aplikasi web ini masih memakai FaceAPI 1.7.15 dan descriptor 128 dimensi yang
  kompatibel dengan referensi tersimpan. Tidak mengklaim memakai ML Kit native
  ataupun MobileFaceNet. [ML Kit Face Detection](https://developers.google.com/ml-kit/vision/face-detection)
  adalah detektor/landmark Android dan iOS, bukan pengenal identitas.
- [Paper MobileFaceNets](https://arxiv.org/abs/1804.07573) menjelaskan alignment
  lima landmark, input RGB 112 × 112, normalisasi (pixel − 127.5)/128 dan model
  embedding terlatih. Pipeline itu tidak boleh diterapkan langsung ke descriptor
  FaceAPI lama atau dianggap kompatibel tanpa model baru dan pendaftaran ulang.
  Threshold perlu divalidasi dengan pasangan foto orang sama dan orang berbeda
  pada perangkat target; angka tidak dapat disalin antar model begitu saja.
- Client `photo-geometry-20261031-v4` mengirim metadata pemeriksaan melalui
  `POST /auth/me/face-diagnostics`. `GET` pada path yang sama hanya menampilkan
  maksimal 10 hasil akun sendiri. Batas keseluruhan 128 akun, disimpan di memori
  proses dan hilang saat restart. Tidak menerima foto, descriptor, atau koordinat
  GPS. Schema menolak field tambahan dan angka non-finite.
- Metadata menyertakan tahap, versi client, ukuran foto/wajah, skor detektor,
  pengukuran tekstur, alasan, serta jarak/threshold jika pencocokan tercapai.
  Ini diperlukan untuk mengetahui penyebab spesifik dari HP yang belum bisa
  direproduksi dengan kamera sintetis.

Request Face Unlock:

```http
POST /devices/{device_id}/unlock
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "face_verified": true,
  "latitude": -7.05,
  "longitude": 110.4,
  "accuracy_m": 9
}
```

Pesan `detail` dari backend (termasuk 400/403/503) ditampilkan di layar. Respons
`command_sent` hanya menyatakan perintah telah dikirim. Aplikasi kemudian memeriksa
status perangkat dan ACK transaksi yang sama melalui
`GET /devices/{device_id}/commands/{transaction_id}`. Setelah 20 detik tanpa ACK,
layar menjelaskan bahwa konfirmasi belum diterima dan tidak otomatis mengirim ulang
perintah. Status pintu fisik ditampilkan terpisah dari keberhasilan command.

Kembali, logout, navigasi, tab disembunyikan, rotasi landscape, dan kamera terputus
menghentikan kamera/membatalkan sesi verifikasi. Respons asinkron sesi lama tidak
dapat memicu request unlock. Request yang sudah terkirim tidak dapat ditarik kembali.

## Daftarkan wajah dari kartu perangkat

Tombol bawah membuka pendaftaran referensi wajah akun owner yang sedang login.
Pemilik akun menyetujui pendaftaran, lalu menekan **Ambil foto** untuk satu selfie.
Referensi baru disimpan setelah **Gunakan foto ini**. Pendaftaran tidak membuka smartlock.
Untuk mendaftarkan akun lain, owner memakai pemilih akun pada Pengaturan → Referensi
Face Unlock. User menggunakan Daftar wajah pada portal pengguna setelah owner
mengizinkan metode wajah; endpoint akun sendiri tidak menerima target akun lain.
Dalam demo, alur kamera dapat dicoba tetapi referensi tidak disimpan.

Tidak ada endpoint bypass umum. Quick access pada portal user hanya dapat dipakai
jika owner memberikan izin metode secara eksplisit; default-nya ditolak/abu-abu.

## API tambahan

| Endpoint | Hak akses | Kegunaan |
|---|---|---|
| `GET /auth/me/face-profile` | Akun aktif | Referensi identitas akun sendiri |
| `PUT /auth/me/face-profile` | Akun dengan izin wajah aktif | Pendaftaran referensi akun sendiri |
| `PUT /auth/users/{id}/face-profile` | Owner | Mendaftarkan referensi foto (profil lama tiga sampel tetap diterima) |
| `DELETE /auth/users/{id}/face-profile` | Owner | Menghapus referensi |
| `GET /devices/{id}/commands/{transaction_id}` | Pembuat command atau owner perangkat | Melihat ACK command bersangkutan |

## Batas akurasi dan kepercayaan

Implementasi memakai `@vladmandic/face-api@1.7.15` (TensorFlow.js), Tiny Face Detector,
68 landmark, dan Face Recognition Net. Versi library/model dipatok; model diunduh
dari jsDelivr saat pertama digunakan. Kamera tidak dikirim ke CDN. Library/model
memerlukan koneksi internet; jika gagal dimuat, verifikasi berhenti dan menyediakan
Coba Lagi. Sumber model/API: [FaceAPI](https://github.com/vladmandic/face-api),
[pencocokan descriptor](https://github.com/vladmandic/face-api/blob/master/TUTORIAL.md).

Kemiringan dihitung dari geometri landmark; yaw/pitch merupakan estimasi rasio,
bukan pengukuran 3D terkalibrasi. Keterlihatan bagian wajah diperiksa dengan
landmark, tekstur, keterbukaan mata, dan pencocokan identitas. Pemeriksaan ini bukan
classifier masker/kacamata/topi khusus dan tidak menjamin seluruh oklusi terdeteksi.
Tidak ada anti-spoof/liveness terverifikasi; foto/video wajah belum dijamin ditolak.
Ambang kualitas dan kecocokan perlu divalidasi pada kamera, pencahayaan, pengguna,
dan kondisi akses nyata sebelum dipakai untuk keamanan produksi.

Kontrak backend proyek tetap memakai client-trust: `face_verified` adalah klaim
client, bukan bukti biometrik bertanda tangan. Alur UI memeriksa wajah sebelum
mengirimkannya, tetapi client yang dimodifikasi dapat memanggil endpoint secara
langsung. Pengamanan produksi membutuhkan pembuktian di server atau perangkat
tepercaya serta challenge anti-replay/liveness. Tidak ada claim keamanan biometrik
produksi dari implementasi prototype ini.

## Pratinjau dan verifikasi

Demo tanpa login dan data dummy frontend telah dihapus. Gunakan akun terautentikasi
pada `/dashboard`; untuk perangkat virtual gunakan launcher backend uji lokal.

- `node scripts/check_face_core.cjs`: kualitas foto, descriptor tidak valid,
  threshold dan pencocokan referensi tunggal/lama.
- `node scripts/check_face_browser.cjs`: kamera sintetis dan keluaran model simulasi;
  memeriksa feedback, identitas, pendaftaran, penolakan GPS, body/header unlock,
  error backend, polling ACK, pendaftaran dari kartu perangkat, dan penghentian kamera. Memerlukan
  Playwright; `PLAYWRIGHT_CHANNEL=msedge` dapat dipakai untuk Edge terpasang.
- `python scripts/check_face_backend.py`: SQLite in-memory dan ASGI, tanpa database
  nyata/MQTT; memeriksa role, privasi profil, pencabutan, validasi, akses command,
  allowlist aset, serta migrasi tambah/hapus tabel.
- `node scripts/check_mobile_dashboard.cjs`: regresi layout mobile/desktop.

Library dan ketiga model asli juga diuji di browser WebGL pada canvas kosong:
model berhasil dimuat dan tidak mendeteksi wajah. Pengujian dengan kamera/wajah
nyata, GPS fisik, database PostgreSQL, dan ESP32 belum dilakukan.
