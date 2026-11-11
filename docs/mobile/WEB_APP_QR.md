# QR Code untuk membuka Web App Smart Lock

QR Web App mengarah langsung ke route FastAPI `/dashboard` pada origin yang
sedang dibuka. Kode QR dibuat di browser menggunakan pustaka QRCode yang sudah
dipakai oleh fitur QR Akses Tamu.

## Cara menggunakan

1. Jalankan backend FastAPI pada port 8000.
2. Buka Web App di laptop melalui alamat yang bisa dijangkau HP:
   - URL HTTPS tunnel/hosting yang sedang aktif; atau
   - alamat IP LAN laptop jika HP dan laptop berada pada Wi-Fi yang sama.
3. Pada halaman login desktop, pindai QR di panel **Buka Smart Lock di HP**.
4. Setelah masuk ke dashboard desktop, tombol **QR HP** di topbar membuka QR
   yang sama. Tautan dapat disalin melalui tombol **Salin tautan Web App**.
5. Pindai QR dengan kamera HP. Browser akan membuka `/dashboard` dan pengguna
   dapat login menggunakan akun masing-masing.

## Catatan penting

- QR dibentuk dari `window.location.origin + /dashboard`; URL ngrok tidak
  di-hardcode. Jika tunnel gratis berubah, buka ulang Web App menggunakan URL
  tunnel terbaru agar QR ikut memakai alamat yang benar.
- Jangan membuat QR dari `localhost` atau `127.0.0.1` untuk dipindai HP karena
  alamat tersebut menunjuk ke perangkat pemindai sendiri. Gunakan IP LAN atau
  HTTPS tunnel/hosting.
- Fitur kamera dan geolokasi browser HP memerlukan HTTPS pada origin publik.
- QR ini hanya membuka Web App. QR Akses Tamu tetap merupakan token akses
  khusus tamu dan tidak boleh disamakan dengan QR Web App.
