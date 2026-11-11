# Smartlock Project 1 — Backend

Backend (FastAPI + PostgreSQL + HiveMQ Cloud) untuk Smartlock Project 1.
Mencakup: autentikasi JWT, manajemen device, MQTT bridge ke ESP32, remote
unlock, manajemen izin akses (`permissions`), QR tamu lengkap dengan halaman
web publiknya, verifikasi lokasi (geofence) + akurasi GPS, audit log, dan
migrasi database (Alembic). Semua fitur di atas sudah diuji end-to-end,
termasuk sudah dicoba langsung ke ESP32 fisik (bukan cuma simulasi).

## Struktur folder

```
smartlock-backend/
├── alembic/
│   ├── versions/             # file-file migration (riwayat perubahan skema)
│   └── env.py                # baca DATABASE_URL otomatis dari .env
├── alembic.ini
├── app/
│   ├── main.py              # entrypoint FastAPI
│   ├── config.py            # baca .env
│   ├── database.py          # koneksi SQLAlchemy
│   ├── models.py            # 5 tabel: users, devices, permissions, guest_access, access_logs
│   ├── schemas.py           # request/response Pydantic
│   ├── auth.py              # hash password, JWT, dependency get_current_user
│   ├── mqtt_client.py       # publisher MQTT (backend -> ESP32, command unlock)
│   ├── static_pages/
│   │   └── guest_page.html   # template halaman web publik buat tamu
│   └── routers/
│       ├── auth_router.py       # /auth/register, /auth/login, /auth/me
│       ├── devices_router.py    # /devices (CRUD + unlock + logs + lokasi/geofence)
│       ├── permissions_router.py # /permissions (CRUD izin akses user biasa)
│       ├── guest_access_router.py # /guest-access (QR tamu: buat, list, cabut, redeem)
│       ├── guest_page_router.py  # /guest/{token} -- halaman web HTML yang dibuka tamu
│       ├── nfc_router.py         # /nfc-cards (CRUD kartu NFC)
│       └── hardware_router.py   # /hardware/* (dipanggil ESP32: ack, heartbeat, event pintu)
├── requirements.txt
└── .env.example
```

## Cara menjalankan di lokal

1. **Install PostgreSQL** (atau pakai Docker: `docker run -d -e POSTGRES_PASSWORD=password -e POSTGRES_DB=smartlock_db -e POSTGRES_USER=smartlock_user -p 5432:5432 postgres:16`)

2. **Buat virtual environment & install dependency**
   ```bash
   python3 -m venv venv
   source venv/bin/activate      # Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **Setup file environment**
   ```bash
   cp .env.example .env
   ```
   Lalu isi `.env`:
   - `DATABASE_URL` → sesuaikan user/password/db PostgreSQL kamu
   - `JWT_SECRET_KEY` → generate random string, contoh: `python3 -c "import secrets; print(secrets.token_hex(32))"`
   - `MQTT_BROKER_HOST`, `MQTT_USERNAME`, `MQTT_PASSWORD` → dari dashboard HiveMQ Cloud (buat cluster gratis dulu di https://www.hivemq.com/mqtt-cloud-broker/)

4. **Jalankan migration database** (bikin semua tabel)
   ```bash
   alembic upgrade head
   ```
   Ini WAJIB dijalankan sebelum start server pertama kali. Kalau berhasil,
   muncul baris `Running upgrade  -> ..., initial schema`.

5. **Jalankan server**
   ```bash
   uvicorn app.main:app --reload
   ```
   (Tabel TIDAK lagi otomatis dibuat saat start seperti sebelumnya — sekarang
   murni lewat migration di langkah 4. Kalau lupa jalanin migration dulu,
   server tetap nyala tapi query ke database bakal error "table not found".)

6. **Buka dokumentasi API interaktif**
   → http://localhost:8000/docs (Swagger UI, bisa langsung coba semua endpoint dari sini)

## Migrasi database (Alembic)

Sebelumnya, skema tabel dibuat otomatis tiap kali server start
(`Base.metadata.create_all`) — masalahnya, begitu ada perubahan model (nambah
kolom, ubah tipe data, dst.), cara itu **tidak bisa** meng-update tabel yang
sudah ada isinya; satu-satunya jalan adalah drop database dan bikin ulang
dari nol (persis yang beberapa kali kita lakuin pas develop kemarin). Sekarang
sudah pakai Alembic, jadi perubahan skema bisa di-ALTER tanpa kehilangan data.

**Kalau ke depannya ada perubahan di `app/models.py`** (nambah tabel baru,
nambah kolom, dsb.), jalankan ini buat generate migration barunya:

```bash
alembic revision --autogenerate -m "deskripsi singkat perubahan"
```

Ini bakal bikin file baru di `alembic/versions/`. **WAJIB dicek dulu isinya**
sebelum dijalankan — autogenerate itu alat bantu, bukan selalu 100% akurat
(kadang ada detail yang perlu ditambah/diperbaiki manual, terutama untuk
perubahan tipe data atau constraint yang kompleks). Setelah dicek dan sesuai,
terapkan ke database:

```bash
alembic upgrade head
```

Kalau mau lihat riwayat migration yang sudah pernah dijalankan:
```bash
alembic history
```

## Endpoint yang sudah tersedia

| Method | Endpoint | Keterangan |
|---|---|---|
| POST | `/auth/register` | Daftar user baru. User **pertama** yang daftar otomatis jadi `owner`, selanjutnya `user`. |
| POST | `/auth/login` | Login (form-data: `username`=email, `password`), balikin JWT. |
| GET | `/auth/me` | Profil user yang lagi login (butuh Bearer token). |
| POST | `/devices/` | Daftarin smart lock baru (khusus `owner`). |
| PATCH | `/devices/{id}/code` | Mengubah `device_code` tanpa menghapus data device (khusus `owner`); kode ini menjadi segmen topic MQTT. |
| GET | `/devices/` | List device (owner lihat semua miliknya, user biasa hanya yang diizinkan). |
| GET | `/devices/{id}` | Detail satu device, termasuk `door_state` dan `lock_status` terkini. |
| PATCH | `/devices/{id}/location` | Owner set/ubah titik lokasi + radius geofence. Begitu diisi, unlock WAJIB kirim lokasi. |
| DELETE | `/devices/{id}/location` | Owner matikan verifikasi lokasi buat device ini. |
| PATCH | `/devices/{id}/access-schedule` | Owner mengatur jam akses pintu global (default 07:00–17:00 WIB). |
| PATCH | `/devices/{id}/face-verification` | Owner aktifkan verifikasi wajah. Begitu aktif, unlock WAJIB kirim `face_verified: true`. |
| DELETE | `/devices/{id}/face-verification` | Owner matikan verifikasi wajah buat device ini. |
| POST | `/devices/{id}/unlock` | **Kirim perintah unlock ke ESP32 lewat MQTT.** Owner selalu boleh; user biasa dicek dari tabel `permissions`. Body `{"latitude", "longitude", "accuracy_m", "face_verified", "nfc_card_uid"}` — field mana yang wajib tergantung verifikasi apa yang diaktifkan per-device. |
| GET | `/devices/{id}/logs` | Lihat audit log (riwayat percobaan akses) untuk satu device — khusus `owner`. |
| POST | `/permissions/` | Owner kasih izin akses device ke user biasa (dicari lewat email). |
| GET | `/permissions/?device_id=...` | List izin yang owner kelola, bisa difilter per device. |
| PATCH | `/permissions/{id}` | Ubah `can_unlock`, jadwal personal, atau `allow_outside_schedule` (pengecualian jam dari admin). |
| DELETE | `/permissions/{id}` | Cabut izin akses user sepenuhnya. |
| POST | `/guest-access/` | Owner bikin akses tamu baru (QR + PIN), balikin `token` buat di-encode jadi QR. |
| GET | `/guest-access/?device_id=...` | List akses tamu, status dihitung real-time (active/expired/used/dll). |
| DELETE | `/guest-access/{id}` | Owner cabut akses tamu sebelum waktunya habis. |
| GET | `/guest-access/{token}` | **Publik, TANPA login** — info ringkas (nama tamu, device, status) sebelum submit PIN. TIDAK berisi PIN. |
| POST | `/guest-access/{token}/redeem` | **Publik, TANPA login** — tamu "tebus" akses pakai PIN setelah scan QR. |
| POST | `/hardware/commands/{command_id}/ack` | **Dipanggil ESP32** (bukan user) setelah command unlock selesai dieksekusi. |
| POST | `/hardware/heartbeat` | **Dipanggil ESP32** tiap 30 detik selama nyala & konek WiFi. Butuh header `X-Device-Uid`. |
| POST | `/hardware/events` | **Dipanggil ESP32** tiap reed switch berubah state (pintu buka/tutup). Butuh header `X-Device-Uid`. |
| POST | `/nfc-cards/` | Owner daftarin kartu/tag NFC baru buat device tertentu. |
| GET | `/nfc-cards/?device_id=...` | List kartu/tag NFC yang terdaftar. |
| PATCH | `/nfc-cards/{id}` | Ubah label atau nonaktifkan sementara (`is_active`). |
| DELETE | `/nfc-cards/{id}` | Hapus kartu/tag permanen. |
| PATCH | `/devices/{id}/nfc-verification` | Owner aktifkan verifikasi NFC. Begitu aktif, unlock WAJIB kirim `nfc_card_uid` yang cocok. |
| DELETE | `/devices/{id}/nfc-verification` | Owner matikan verifikasi NFC buat device ini. |

Selain endpoint JSON di atas, ada satu **halaman web** (bukan API JSON):
**`GET /guest/{token}`** — halaman HTML lengkap yang dibuka tamu setelah scan
QR (lihat bagian "Halaman web publik buat tamu" di bawah). Endpoint ini
sengaja disembunyikan dari Swagger (`/docs`) karena bukan bagian dari API
contract, tapi tetap bisa diakses langsung lewat browser.

## Alur unlock end-to-end (sudah disesuaikan dengan firmware asli)

> ⚠️ Update dari versi sebelumnya: awalnya kupikir ESP32 bakal publish balik
> status/hasil lewat topik MQTT (`smartlock/{device_code}/status` & `.../event`).
> Setelah cek `FIRMWARE_INTEGRATION_ADDENDUM_UPDATE.md`, ternyata firmware yang beneran
> jalan itu **cuma nerima command lewat MQTT**, lalu balikin konfirmasi/status **lewat
> HTTP POST ke backend**, bukan publish MQTT lagi. Kode di paket ini sudah disesuaikan
> ke perilaku firmware yang sebenarnya.

1. Kamu panggil `POST /devices/{id}/unlock` (habis login).
2. Backend cek izin di tabel `permissions` (kalau bukan owner).
3. Backend generate `command_id` (UUID) unik, lalu **publish** ke topik MQTT
   `smartlock/{device_code}/commands` (perhatikan: **plural**, bukan `/command`) isinya:
   ```json
   {"command_id": "...", "action": "unlock"}
   ```
4. Response langsung balik `status: "command_sent"` — **ini BUKAN konfirmasi kunci
   beneran kebuka**, cuma konfirmasi "perintah udah dikirim ke broker".
5. Firmware ESP32 (Ridho) subscribe ke topik itu, cek `action == "unlock"`, aktifin
   solenoid (GPIO 5) selama 3 detik (hardcoded, belum bisa diatur dari backend),
   lalu kirim **HTTP POST** ke `/hardware/commands/{command_id}/ack` dengan body
   `{"status": "success"}`.
6. Backend cocokin `command_id` itu dengan `transaction_id` di tabel `access_logs`,
   lalu update baris tersebut dari `pending` jadi `success`/`failed`.
7. Firmware juga kirim **HTTP POST** `/hardware/heartbeat` tiap 30 detik (update
   `devices.status` jadi online/offline) dan `/hardware/events` tiap reed switch
   berubah (update `devices.door_state` jadi open/closed).

**Penting soal `device_code`**: field ini di database kita = `device_uid` di dokumen
firmware (istilah beda, konsep sama — identifier unik per perangkat, contoh:
`LOCK-LAB-01`). Pastikan `device_code` yang kamu daftarkan lewat `POST /devices/`
**persis sama** dengan `device_uid` yang di-hardcode di firmware ESP32; kalau beda
huruf/kapital sedikit aja, backend gak akan bisa mencocokkan device-nya.

## Yang SENGAJA tidak diimplementasikan dari dokumen firmware

Dokumen `FIRMWARE_INTEGRATION_ADDENDUM_UPDATE.md` juga menyebut beberapa hal yang
kelihatannya bagian dari sistem lain (kemungkinan project magang terpisah, bukan
Smartlock Project 1 ini), jadi **tidak** diikutkan di backend ini:
- BLE proximity (`ble_service_uuid`, `/mobile/mahasiswa/ble/challenges`,
  `/hardware/ble-attestations`) — sistem verifikasi kedekatan via Bluetooth untuk
  mahasiswa, di luar scope MVP kalian (lokasi kalian pakai GPS, bukan BLE).
- `POST /admin/hardware-devices` — endpoint provisioning device dengan skema admin
  berbeda dari `POST /devices/` yang sudah ada di backend ini.
- Header `X-Device-Secret` — validasi autentikasi device belum diimplementasikan
  (lihat catatan keamanan di `app/routers/hardware_router.py`). Untuk demo/lab masih
  aman karena jaringan tertutup, tapi kalau mau lebih ketat sebelum dipakai lebih luas,
  ini perlu ditambah.

Kalau ternyata sebagian dari ini justru relevan buat Smartlock Project 1 (bukan cuma
project magang), kabari aku ya, bisa diintegrasikan.

## Kenapa desainnya begini (biar nyambung sama dokumen rencana kelompok)

- **5 tabel** persis sesuai yang direncanakan Nia: `users`, `devices`,
  `permissions`, `guest_access`, `access_logs`.
- **Role owner/user** dari awal, karena dokumen jelas bilang Owner beda hak
  akses dari User biasa (guest ditangani terpisah lewat tabel `guest_access`
  + token, bukan lewat akun).
- **`device_code`** (mis. `LOCK-LAB-01`) dipisah dari `id` (UUID internal) karena
  `device_code` inilah yang dipakai di topik MQTT
  (`smartlock/LOCK-LAB-01/commands`, dst.) dan di header `X-Device-Uid` dari firmware.
- Field `geofence_radius_m`, `latitude`, `longitude` di tabel `devices`
  dipakai buat fitur verifikasi lokasi (Bab 9 dokumen) — lihat bagian
  "Verifikasi lokasi (geofence)" di bawah buat detail lengkapnya.

## Alur QR tamu (penting buat dipahami tim Nabil/website)

1. Owner panggil `POST /guest-access/` — isi `guest_name`, `valid_from`, `valid_until`,
   `max_uses`. `pin_otp` boleh dikosongkan (backend generate 6 digit otomatis).
2. Response-nya kasih `token` (string acak panjang) dan `pin_otp`. **Aplikasi/website
   yang bikin QR-nya dari `token` ini** — backend cuma kasih data mentah, bukan
   gambar QR (generate QR image itu tugas frontend, banyak library gratis buat itu,
   mis. `qr_flutter` di Flutter).
3. QR + PIN dibagikan ke tamu (WhatsApp/email/ditampilin langsung), sesuai rancangan
   di dokumen project: "QR sementara + PIN/OTP", bukan QR polos tanpa verifikasi tambahan.
4. Tamu scan QR → browser otomatis buka halaman **`GET /guest/{token}`** (sudah
   dibuatin di backend ini, lihat bagian "Halaman web publik buat tamu" di
   bawah, gak perlu tunggu tim website lagi) → halaman itu minta tamu masukin
   PIN → panggil `POST /guest-access/{token}/redeem` dengan body `{"pin_otp": "..."}`.
5. Backend validasi: token ada, belum di-revoke, sudah masuk rentang
   `valid_from`-`valid_until`, belum melebihi `max_uses`, dan PIN cocok. Kalau semua
   lolos, backend kirim command unlock ke ESP32 (proses sama persis kayak
   `POST /devices/{id}/unlock`) dan tambah `use_count`.
6. Semua percobaan (berhasil, PIN salah, kedaluwarsa, dll) tercatat di `access_logs`
   dengan `method: "qr"` dan `guest_access_id` terisi, biar kelihatan di riwayat.

**Status ditentukan real-time**, bukan disimpan statis — jadi kalau kamu bikin QR
valid besok jam 2 siang, sekarang statusnya otomatis `"not_started"`, begitu jam 2
siang lewat otomatis `"active"` tanpa perlu ada proses/cron terpisah yang update
database. Satu-satunya status yang benar-benar "disimpan" adalah `"revoked"` (karena
itu keputusan eksplisit owner, bukan hasil hitungan waktu).

## Halaman web publik buat tamu (QR redeem)

Beda dari rencana awal, **halaman web-nya sekarang udah dibuatin di backend
ini juga** (`app/static_pages/guest_page.html`, di-serve lewat
`GET /guest/{token}`), jadi gak perlu ditunggu dari tim website/Nabil lagi.

Cara pakainya:
1. Bikin akses tamu lewat `POST /guest-access/`, dapet `token` dan `pin_otp`.
2. QR code yang di-generate (di aplikasi/dashboard) isinya URL:
   ```
   {base_url}/guest/{token}
   ```
   Contoh: `https://<domain-aktif>/guest/<token>` (gunakan domain dan token akses tamu yang baru dibuat; URL tunnel lama tidak berlaku).
3. Tamu scan QR itu, browser otomatis buka halaman ini (gak perlu install
   apapun), halaman nampilin nama tamu + nama device + minta PIN.
4. Setelah PIN benar dan disubmit, halaman ini yang manggil
   `POST /guest-access/{token}/redeem` secara otomatis lewat JavaScript.

Halaman ini murni file statis (HTML+CSS+JS jadi satu, gak butuh proses build
apapun), semua logic validasi (PIN salah, kedaluwarsa, limit habis, dll)
tetap murni di backend lewat endpoint yang sama kayak yang API contract-nya
sudah didokumentasikan buat Nabil — halaman ini cuma "wajah" buat endpoint
yang sama, bukan logic terpisah.

**Kalau desainnya mau diubah** (warna, teks, dll), tinggal edit file
`app/static_pages/guest_page.html` langsung — gak perlu compile/build apapun,
tinggal save dan refresh browser.

## Verifikasi lokasi (geofence) di endpoint unlock

Field `latitude`, `longitude`, `geofence_radius_m` di tabel `devices` (yang
tadinya nganggur) sekarang beneran dipakai:

1. Default-nya **mati** — device baru dibuat tanpa geofence, endpoint unlock
   jalan normal tanpa perlu kirim lokasi sama sekali (persis kayak sebelumnya).
2. Owner **aktifkan** verifikasi lokasi lewat `PATCH /devices/{id}/location`,
   isi titik koordinat device + radius yang diizinkan (meter).
3. Begitu aktif, `POST /devices/{id}/unlock` **wajib** dikasih body
   `{"latitude": ..., "longitude": ..., "accuracy_m": ... (opsional)}` (dari GPS HP
   tamu/user). Backend hitung jarak pakai formula haversine (`app/geo.py`),
   bandingkan sama radius:
   - `accuracy_m` dikirim dan lebih buruk dari 50m (`DEFAULT_MAX_GPS_ACCURACY_M`
     di `app/geo.py`) → `400`, ditolak duluan sebelum sempat cek jarak (GPS lagi
     gak akurat, mending diminta ulang daripada geofence salah putusan)
   - Di luar radius → `403`, dicatat ke `access_logs` dengan koordinat + jarak aslinya
   - Lokasi gak dikirim padahal geofence aktif → `400`
   - Dalam radius → lanjut proses unlock seperti biasa
4. Owner bisa **matikan** lagi kapan aja lewat `DELETE /devices/{id}/location`.

Semua percobaan (berhasil maupun ditolak) tercatat lengkap di `access_logs`
termasuk koordinat dan akurasi GPS yang dikirim, jadi bisa diaudit siapa
mencoba unlock dari mana dan seberapa akurat data lokasinya.

## Lingkup versi saat ini (tanpa presensi)

Pada versi ini, fitur presensi dan modul akademik tidak digunakan. Endpoint
aktif tidak mendaftarkan router periode akademik, mata kuliah, rombel, pengampu,
jadwal kuliah, ataupun presensi. Alur NFC dan verifikasi wajah digunakan untuk
mengendalikan akses pintu dan menghasilkan `access_logs`, bukan membuat data
kehadiran.

Tabel/model akademik lama masih ada di source agar upgrade database yang sudah
pernah dipakai tidak menghapus data secara otomatis. Tabel tersebut tidak
terhubung ke menu dashboard atau API aktif. Untuk pengembangan fitur saat ini,
fokus pada user, permission, NFC, autentikasi wajah, geofence, jadwal akses pintu,
perangkat, guest access, dan log keamanan.

## Verifikasi identitas: wajah, NFC, dan geofence

Sistem mendukung NFC dan verifikasi wajah sebagai jalur autentikasi. NFC dicek
oleh backend terhadap kartu aktif pada perangkat dan, bila kartu ditautkan ke
akun, hanya akun pemilik kartu yang boleh menggunakannya. Verifikasi wajah
menerima hasil `face_verified` dari client; backend belum menghitung embedding
wajah sendiri, sehingga client tidak boleh mengirim `true` tanpa melakukan
pencocokan wajah nyata.

Jika geofence diaktifkan pada perangkat, akses berbasis wajah/manual harus
mengirim koordinat yang memenuhi radius dan batas akurasi GPS. NFC yang valid
menjadi bukti proximity fisik sehingga alur tersebut tidak meminta validasi
GPS tambahan. Semua percobaan akses yang berhasil maupun ditolak dicatat pada
`access_logs`; tidak ada pembuatan data presensi dalam versi ini.

Urutan pengaturan oleh admin:

1. Daftarkan kartu/tag lewat `POST /nfc-cards/` bila NFC akan digunakan.
2. Aktifkan NFC lewat `PATCH /devices/{id}/nfc-verification` atau verifikasi
   wajah lewat `PATCH /devices/{id}/face-verification`.
3. Bila validasi lokasi dibutuhkan, atur titik dan radius lewat
   `PATCH /devices/{id}/location`.
4. Berikan izin perangkat ke pengguna melalui `POST /permissions/`.
5. Atur jam akses melalui `PATCH /devices/{id}/access-schedule`, default
   **07:00–17:00 WIB**. Untuk mengecualikan pengguna tertentu dari batas jam,
   admin mengaktifkan `allow_outside_schedule` pada permission pengguna itu.

## Langkah selanjutnya (belum dikerjakan)

MQTT bridge, endpoint unlock, CRUD `permissions`, QR tamu (`guest_access`),
halaman web tamu, migrasi database Alembic, verifikasi lokasi, verifikasi
wajah (Opsi A), dan verifikasi NFC via HP **sudah selesai** di sisi backend.
Sisa roadmap:

1. **Audit log dashboard** — endpoint `GET /devices/{id}/logs` udah ada, tinggal dikonsumsi
   di halaman Website Dashboard (punya Nia).
2. **Verifikasi wajah Opsi B (embedding, lebih aman)** — kalau nanti dibutuhkan
   keamanan lebih ketat, ini yang perlu didesain ulang bareng Nabil.

Saran: setelah firmware ESP32 Ridho siap subscribe/publish sesuai format topik di atas,
langsung coba tes `POST /devices/{id}/unlock` dari Swagger UI — itu momen paling seru,
kamu bakal lihat solenoid-nya nyala dari perintah HTTP. 🔓


## Konfigurasi ESP32 `LOCK-LAB-01` dan NFC melalui HP

Untuk konfigurasi firmware yang memakai `DEVICE_UID = "LOCK-LAB-01"`, pastikan baris `device_code` milik device yang sama di database juga tepat `LOCK-LAB-01`. Backend membentuk topic command dari kode yang tersimpan di database, yaitu `smartlock/LOCK-LAB-01/commands`. `MQTT_CLIENT_ID` pada ESP32 adalah nama sesi klien broker; nilainya tidak dipakai backend untuk menentukan topic, tetapi tetap harus unik di broker.

Jika device sudah terdaftar dengan kode lama (misalnya `DEMOESP`), owner dapat mengubahnya tanpa menghapus kartu NFC, permission, jadwal, maupun riwayat menggunakan endpoint baru:

```http
PATCH /devices/{device_id}/code
Authorization: Bearer <token-owner>
Content-Type: application/json

{
  "device_code": "LOCK-LAB-01"
}
```

`device_id` pada URL adalah ID internal/UUID yang didapat dari `GET /devices/`, bukan `device_code`. Kode baru harus unik dan hanya boleh berisi huruf, angka, tanda hubung (`-`) atau garis bawah (`_`). Jika kode sudah digunakan device lain, backend mengembalikan HTTP 409. Endpoint ini tidak memerlukan migration database.

Flow NFC untuk setup tanpa modul PN532 di ESP32:
1. Aplikasi HP membaca UID dari kartu/tag NFC.
2. Aplikasi mengirim `POST /devices/{device_id}/unlock` dengan `nfc_card_uid` dan token login user.
3. Pastikan NFC verification aktif dan UID telah didaftarkan pada device yang sama lewat `/nfc-cards/`. User biasa juga harus punya permission `can_unlock=true` untuk device tersebut.
4. Backend menerbitkan MQTT ke `smartlock/LOCK-LAB-01/commands`; ESP32 menerima command dan membuka GPIO solenoid. ESP32 mengirim ACK lewat HTTP agar hasil akses pada log diperbarui.

Catatan: `/hardware/nfc-verify` dipakai untuk flow alternatif jika reader PN532 dipasang langsung ke ESP32; endpoint itu tidak perlu dipanggil oleh aplikasi HP pada konfigurasi ini.

## Demo akses pintu (tanpa presensi)

Untuk demo aplikasi/Swagger dengan device `LOCK-LAB-01`:

1. Owner memastikan perangkat terdaftar serta jam akses pintu telah diatur pada Dashboard > Devices > **Jadwal Akses Pintu** (default 07:00–17:00 WIB).
2. Owner mendaftarkan UID kartu pada device dan, jika ingin mengidentifikasi pemiliknya, mengaitkan kartu ke akun pengguna. Aktifkan verifikasi NFC bila fitur itu digunakan.
3. Berikan akun pengguna permission `can_unlock=true` pada perangkat. Untuk pengecualian di luar jadwal, owner dapat mengaktifkan `allow_outside_schedule` pada permission pengguna tersebut.
4. Pengguna login ke aplikasi/Swagger dan memanggil `POST /devices/{device_id}/unlock`. Untuk NFC, kirim `nfc_card_uid`; untuk wajah, kirim hasil `face_verified=true` hanya setelah verifikasi wajah nyata dilakukan oleh client. Jika geofence aktif, kirim koordinat yang memenuhi radius.
5. Backend memeriksa izin pengguna dan jam operasional. Di luar jam, pengguna biasa ditolak kecuali memiliki izin di luar jam yang diberikan admin. Owner dapat menjalankan unlock manual kapan saja.
6. Jika valid, backend menerbitkan MQTT ke `smartlock/LOCK-LAB-01/commands`. ESP32 harus menerima command dan menggerakkan solenoid, kemudian mengirim ACK melalui `POST /hardware/commands/{command_id}/ack`.
7. Periksa hasilnya lewat log akses perangkat (`GET /devices/{device_id}/logs`) dan status pintu/kunci yang dilaporkan ESP32. Respons `status: "command_sent"` hanya berarti perintah telah dikirim; itu belum membuktikan solenoid benar-benar bergerak sampai ada ACK dari hardware.

Catatan: endpoint face pada prototipe menerima hasil `face_verified` dari client; backend belum menghitung embedding wajah sendiri. Karena itu client tidak boleh mengirim `true` tanpa verifikasi wajah nyata.

## Catatan pembaruan dashboard (Jadwal & NFC)
Dashboard terbaru menampilkan jadwal dalam bentuk kartu dengan ringkasan, pencarian, dan filter hari/ruangan/periode akademik. Pada menu Kartu NFC, pemilik kartu dapat dipilih dari daftar nama/email user aktif. Tombol `Kaitkan User` / `Ganti User` membuka dropdown pemilih akun, sedangkan `Lepas User`, aktivasi/nonaktif kartu, dan hapus kartu tetap tersedia. Endpoint tetap memakai `/auth/users` dan `/nfc-cards`; tidak memerlukan migrasi database baru.


## Jam akses pintu (fitur baru)

Setiap perangkat memiliki jam akses global yang default-nya **07:00–17:00 WIB**. Jam ini dikelola owner/admin lewat Dashboard > Devices > Jadwal Akses Pintu atau endpoint `PATCH /devices/{device_id}/access-schedule`. Di luar rentang tersebut, akses user biasa melalui unlock/NFC/wajah dan akses tamu ditolak. Owner/admin tetap dapat membuka secara manual lewat akun owner.

Admin juga dapat memberi pengecualian per pengguna lewat Dashboard > Permissions > **Izinkan akses di luar jam pintu**. Pengecualian ini tidak menghapus validasi geofence atau jam personal pengguna yang secara opsional diatur di permission. Waktu operasional menggunakan WIB (UTC+7). Interval mengikuti pola mulai inklusif dan waktu tutup eksklusif: pada tepat jam tutup, akses reguler sudah ditolak. Rentang yang melewati tengah malam juga didukung.

Sesudah mengganti kode, jalankan migrasi database:

```powershell
.\venv\Scripts\Activate.ps1
alembic upgrade head
python -m uvicorn app.main:app --reload --port 8000
```

Menu akademik dan endpoint presensi tidak lagi didaftarkan pada aplikasi aktif. Tabel akademik lama sengaja tidak dihapus oleh migrasi agar tidak menghapus data lama secara permanen.

### Penghapusan modul akademik/presensi

Versi ini tidak lagi memakai tabel akademik dan presensi. Migrasi `b7e26c4d91a0` menghapus tabel `academic_periods`, `courses`, `rombels`, `rombel_members`, `course_assignments`, `schedules`, `attendances`, serta kolom `users.academic_role`. Data akun, perangkat, izin, kartu NFC, akses tamu, dan log akses tetap dipertahankan. Backup database terlebih dahulu sebelum menjalankan `alembic upgrade head`, karena data lama akademik/presensi akan dihapus.


## Login dengan Google (Web Admin)

Login Google memakai Google Identity Services. Backend memverifikasi ID token menggunakan library `google-auth`; jangan percaya nama/email yang hanya dikirim oleh browser. Endpoint yang ditambahkan:

- `GET /auth/google/config`: memberi tahu frontend apakah Google Client ID sudah dikonfigurasi.
- `POST /auth/google` dengan JSON `{ "credential": "<Google ID token>" }`: memverifikasi token dan mengembalikan JWT Smart Lock serta data user.

### Konfigurasi

1. Buka Google Cloud Console dan pilih/buat project.
2. Siapkan Google Auth Platform / OAuth consent screen. Untuk testing, tambahkan akun Google yang akan diuji sebagai test user jika aplikasi masih berstatus Testing.
3. Buat OAuth Client ID dengan tipe **Web application**. Tambahkan origin website pada **Authorized JavaScript origins**, misalnya `http://localhost:8000` dan URL HTTPS ngrok yang sedang dipakai. Google Identity Services ID-token button tidak memerlukan redirect URI callback khusus karena callback JavaScript mengirim credential ke backend.
4. Salin Web Client ID ke `.env` di root `smartlock-backend`:

   `GOOGLE_CLIENT_ID=xxxx.apps.googleusercontent.com`

5. Jalankan sekali `pip install -r requirements.txt`, lalu restart Uvicorn. Buka dashboard dan lakukan hard refresh (`Ctrl+F5`).
6. Email Google harus sudah terdaftar di Smart Lock dan akun harus aktif. Jika belum, daftar dulu melalui tab Daftar Akun dengan alamat email yang sama. Login Google tidak membuat akun baru otomatis dan tidak mengubah role.

**Keamanan:** jangan taruh Client Secret di frontend atau kirim ke chat. Client ID memang digunakan di browser; token ID tetap diverifikasi oleh backend. Gunakan HTTPS/ngrok HTTPS saat mengakses dari perangkat lain.


## Tampilan Web App dan QR akses HP

Web App tersedia pada route `/dashboard`. Layout menggunakan tampilan portrait
pada HP dan dashboard lebar pada laptop/PC. Pada HP, orientasi landscape
menampilkan instruksi untuk kembali ke portrait. Pada laptop/PC, dashboard
menggunakan ruang horizontal.

Halaman login desktop menyediakan QR Code **Buka Smart Lock di HP** dan
dashboard desktop menyediakan tombol **QR HP**. QR dibuat dari alamat origin
yang sedang aktif ditambah `/dashboard`, sehingga tidak bergantung pada URL
ngrok lama. Untuk memindai dari HP, buka Web App melalui URL HTTPS tunnel/
hosting yang aktif atau IP LAN yang dapat dijangkau HP. `localhost` tidak dapat
dipakai sebagai tujuan QR dari perangkat lain.

Dokumentasi: `docs/mobile/README.md` dan `docs/mobile/WEB_APP_QR.md`.
