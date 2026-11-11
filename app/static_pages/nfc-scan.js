/* Web NFC helper for owner/user card enrollment. Reads tag serialNumber only. */
(function () {
  'use strict';
  let activeScan = null;

  function setStatus(id, message, state = '') {
    const node = document.getElementById(id);
    if (!node) return;
    node.textContent = message;
    node.dataset.state = state;
    node.hidden = !message;
  }

  function normalizeSerialNumber(value) {
    const raw = String(value || '').trim();
    if (!raw) return '';
    const compact = raw.replace(/[^0-9a-f]/gi, '').toUpperCase();
    if (compact && compact.length >= 8 && compact.length <= 32 && compact.length % 2 === 0) {
      return compact.match(/.{2}/g).join(':');
    }
    return raw.replace(/-/g, ':').replace(/\s+/g, '').toUpperCase();
  }

  function stopNfcUidScan(message = '', statusState = 'info') {
    const session = activeScan;
    if (!session) return;
    activeScan = null;
    clearTimeout(session.timer);
    try { session.controller.abort(); } catch (_) {}
    if (session.button && session.button.isConnected) {
      session.button.disabled = false;
      session.button.innerHTML = session.originalHtml;
      session.button.removeAttribute('aria-busy');
    }
    if (message) setStatus(session.statusId, message, statusState);
  }

  async function scanNfcUid(inputId, statusId, buttonId) {
    const input = document.getElementById(inputId);
    const button = document.getElementById(buttonId);
    if (!input || !button || button.disabled) return;
    stopNfcUidScan();

    if (!window.isSecureContext) {
      setStatus(statusId, 'Pemindaian NFC memerlukan HTTPS. Buka dashboard melalui alamat HTTPS.', 'error');
      return;
    }
    if (!('NDEFReader' in window)) {
      setStatus(statusId, 'Browser ini belum mendukung Web NFC. Gunakan Chrome Android yang mendukung NFC, atau masukkan UID dari reader secara manual.', 'error');
      return;
    }

    const controller = new AbortController();
    const reader = new NDEFReader();
    const session = { controller, reader, input, button, statusId, originalHtml: button.innerHTML, timer: null };
    activeScan = session;
    button.disabled = true;
    button.textContent = 'Menunggu kartu…';
    button.setAttribute('aria-busy', 'true');
    setStatus(statusId, 'NFC aktif. Tempelkan kartu/tag ke bagian belakang HP dan tahan sebentar.', 'info');

    reader.addEventListener('reading', event => {
      if (activeScan !== session) return;
      const uid = normalizeSerialNumber(event.serialNumber);
      if (!uid) {
        stopNfcUidScan('Tag terdeteksi, tetapi browser tidak memberikan UID. Coba kartu NDEF lain atau gunakan reader PN532/manual.', 'error');
        return;
      }
      input.value = uid;
      input.dispatchEvent(new Event('input', { bubbles: true }));
      input.dispatchEvent(new Event('change', { bubbles: true }));
      stopNfcUidScan('UID berhasil dibaca: ' + uid + '. Periksa nama kartu, lalu tekan Daftarkan.');
    }, { signal: controller.signal });

    reader.addEventListener('readingerror', () => {
      if (activeScan === session) {
        setStatus(statusId, 'Tag tidak dapat dibaca sebagai NDEF. Beberapa kartu tidak didukung Web NFC; coba kartu lain atau masukkan UID secara manual.', 'error');
      }
    }, { signal: controller.signal });

    session.timer = setTimeout(() => {
      if (activeScan === session) stopNfcUidScan('Waktu pemindaian habis. Tekan Pindai dengan HP untuk mencoba lagi.');
    }, 30000);

    try {
      await reader.scan({ signal: controller.signal });
    } catch (error) {
      if (activeScan !== session) return;
      const messages = {
        NotAllowedError: 'Izin NFC ditolak. Izinkan situs ini menggunakan NFC dari dialog browser.',
        NotSupportedError: 'Perangkat atau browser tidak mendukung Web NFC, atau NFC HP sedang tidak tersedia.',
        SecurityError: 'Web NFC hanya dapat digunakan pada halaman HTTPS dan tab utama browser.',
        InvalidStateError: 'NFC tidak dapat dimulai. Pastikan NFC HP aktif dan tidak sedang dipakai aplikasi lain.',
      };
      stopNfcUidScan(messages[error.name] || ('Pemindaian NFC gagal: ' + (error.message || 'coba lagi.')), 'error');
    }
  }

  document.addEventListener('visibilitychange', () => {
    if (document.hidden) stopNfcUidScan('Pemindaian dihentikan karena halaman tidak aktif.');
  });
  window.addEventListener('pagehide', () => stopNfcUidScan());
  window.scanNfcUid = scanNfcUid;
  window.stopNfcUidScan = stopNfcUidScan;
})();
