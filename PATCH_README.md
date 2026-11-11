# PATCH Smart Lock – Dashboard User, NFC Scan, dan Landscape

Patch ini berisi **file yang berubah saja**. Tidak ada file `.env`, kredensial,
database, referensi wajah, virtual environment, atau cache yang disertakan.

## Cara memasang

1. Buat salinan/backup folder proyek Smart Lock yang sekarang.
2. Ekstrak seluruh isi ZIP patch ini **ke dalam folder root proyek `smartlock-backend`**
   yang berisi folder `app`, `scripts`, `docs`, dan `requirements.txt`.
3. Saat Windows menanyakan apakah file yang sama perlu diganti, pilih **Replace / Ganti file**.
4. Restart backend FastAPI agar allowlist aset `nfc-scan.js` ikut dimuat.
5. Buka kembali `/dashboard` melalui HTTPS di HP dan lakukan refresh penuh (Ctrl+F5 di desktop).

ZIP ini memakai path relatif proyek, misalnya `app/static_pages/dashboard.html`.
Jangan mengekstraknya satu tingkat di atas folder proyek.

## Perubahan

- User yang sudah login dapat membuka dashboard, beranda, dan profil meskipun belum memiliki permission perangkat.
- User dapat mendaftarkan referensi wajah milik akun sendiri tanpa permission perangkat. Pendaftaran tidak memberi izin unlock dan tidak mengubah role.
- Owner tetap mengatur permission perangkat dan metode unlock. Memberi permission tidak mengubah role user menjadi owner/admin.
- Form NFC owner dan user mendapat tombol **Pindai dengan HP** menggunakan Web NFC; UID otomatis diisi dari `serialNumber` jika tag/browser mendukungnya.
- UID manual tetap tersedia sebagai fallback.
- Dashboard dan layar Face Unlock mendukung orientasi landscape; pemblokir portrait telah dihapus.
- Dokumentasi dan skrip pengujian diperbarui.

## Catatan NFC

Web NFC memerlukan HTTPS, halaman utama (bukan iframe), izin browser, NFC HP aktif,
dan browser Android yang mendukung Web NFC. API browser terbatas pada tag NDEF.
Tag yang tidak mendukung NDEF, tag dengan serial number kosong, atau protokol NFC
low-level/HCE tidak dapat dipindai melalui browser ini. Untuk kondisi tersebut,
gunakan input UID manual dari reader/PN532 atau aplikasi Android native yang sesuai.

User hanya dapat mendaftarkan kartu setelah owner memberikan izin NFC pada perangkat
tertentu, karena kartu harus terikat ke perangkat. Ini berbeda dari akses dashboard:
login dan profil user tidak memerlukan permission perangkat.

## Database

Tidak ada perubahan skema database dan tidak diperlukan migrasi Alembic untuk patch ini.
