/* Camera lifecycle, TF.js face recognition, owner enrollment, GPS and command ACK. */
(function () {
  'use strict';
  const Core = window.SmartlockFaceCore;
  const CDN = 'https://cdn.jsdelivr.net/npm/@vladmandic/face-api@1.7.15';
  let modelPromise = null, current = null, sequence = 0;
  const patchCanvas = document.createElement('canvas');
  patchCanvas.width = patchCanvas.height = 64;
  const patchContext = patchCanvas.getContext('2d', { willReadFrequently: true });
  const faceIcon = '<svg viewBox="0 0 64 64" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 8H9v10M46 8h9v10M9 46v10h9M55 46v10h-9"/><ellipse cx="32" cy="31" rx="16" ry="21"/><path d="M24 27h2m12 0h2M30 28v9h5M25 43c4 3 10 3 14-1"/></svg>';

  function screen() {
    let el = document.getElementById('face-screen');
    if (el) return el;
    el = document.createElement('section');
    el.id = 'face-screen'; el.className = 'face-screen'; el.hidden = true;
    el.setAttribute('role', 'dialog'); el.setAttribute('aria-modal', 'true'); el.setAttribute('aria-labelledby', 'face-status');
    el.innerHTML = '<header class="face-top"><button class="face-back" type="button" aria-label="Kembali">←</button><span id="face-device-label"></span></header>' +
      '<div class="face-content"><span class="face-simulation-badge" hidden>SIMULASI · Smartlock virtual</span>' +
      '<h1 id="face-status" class="face-status" role="status" aria-live="polite"></h1>' +
      '<div class="face-oval"><video id="face-video" autoplay muted playsinline aria-label="Kamera depan untuk verifikasi wajah"></video><img id="face-photo" alt="Foto wajah Anda untuk diperiksa sebelum pendaftaran" hidden><div class="face-placeholder">' + faceIcon + '</div><div class="face-success-mark" aria-hidden="true">✓</div></div>' +
      '<p class="face-hint" id="face-hint"></p><div class="face-controls"><button id="face-retry" class="face-primary" hidden>Coba Lagi</button><button id="face-consent" class="face-primary" hidden>Saya setuju, mulai kamera</button><button id="face-take-photo" class="face-primary" hidden>Ambil foto</button><button id="face-save-photo" class="face-primary" hidden>Gunakan foto ini</button><button id="face-retake" hidden>Ambil ulang</button><button id="face-done" hidden>Kembali ke dashboard</button></div>' +
      '</div>';
    document.getElementById('app-root').append(el);
    const appearance = document.querySelector('.topbar-actions .appearance-switch').cloneNode(true);
    el.querySelector('.face-top').append(appearance);
    const back = el.querySelector('.face-back');
    back.setAttribute('aria-label', 'Kembali ke Beranda');
    back.innerHTML = '← <span>Beranda</span>';
    const returnHome = () => { close(); goTo('overview'); };
    back.addEventListener('click', returnHome);
    el.querySelector('#face-done').textContent = 'Kembali ke Beranda';
    el.querySelector('#face-done').addEventListener('click', returnHome);
    el.querySelector('#face-retry').addEventListener('click', () => {
      if (!current) return;
      const { deviceId, mode, targetUser, targetName } = current;
      open(deviceId, { mode, targetUser, targetName, consent: mode === 'enroll' });
    });
    el.querySelector('#face-consent').addEventListener('click', () => {
      if (!current || current.mode !== 'enroll') return;
      el.querySelector('#face-consent').hidden = true;
      begin(current);
    });
    el.querySelector('#face-save-photo').addEventListener('click', () => { if(current) saveEnrollment(current); });
    el.querySelector('#face-take-photo').addEventListener('click', () => { if(current) takePhoto(current); });
    el.querySelector('#face-retake').addEventListener('click', () => {
      if (!current) return;
      const { targetUser, targetName } = current;
      open(current.deviceId, { mode: current.mode, targetUser, targetName, consent: true });
    });
    el.addEventListener('keydown', event => {
      if (event.key === 'Escape') { event.preventDefault(); close(); }
      if (event.key !== 'Tab') return;
      const buttons = [...el.querySelectorAll('button,input')].filter(x => !x.disabled && x.getClientRects().length);
      if (!buttons.length) return;
      if (event.shiftKey && document.activeElement === buttons[0]) { event.preventDefault(); buttons[buttons.length - 1].focus(); }
      else if (!event.shiftKey && document.activeElement === buttons[buttons.length - 1]) { event.preventDefault(); buttons[0].focus(); }
    });
    return el;
  }
  function active(run) { return current === run && !run.controller.signal.aborted && state.user && state.user.id === run.userId && state.token === run.token; }
  function diagnostic(run, stage, reason, comparison = null) {
    if(!run.token || state.user?.id!==run.userId || state.token!==run.token) return;
    const sample=run.photoMetrics, q=sample?.quality, src=sample?.source;
    const report={client_version:Core.CLIENT_VERSION,mode:run.mode,stage,reason:String(reason).slice(0,500)};
    const metrics={detector_score:sample?.score,image_width:src?.width,image_height:src?.height,face_width:src?.faceWidth,face_height:src?.faceHeight,brightness:q?.brightness,sharpness:q?.sharpness,eye_texture:q?.eyeTexture,nose_texture:q?.noseTexture,mouth_texture:q?.mouthTexture,distance:comparison?.distance,threshold:comparison?.threshold};
    Object.entries(metrics).forEach(([key,value])=>{if(Number.isFinite(value))report[key]=Math.round(value*10000)/10000;});
    fetch(state.apiBase+'/auth/me/face-diagnostics',{method:'POST',headers:{'Content-Type':'application/json',Authorization:'Bearer '+run.token},body:JSON.stringify(report),keepalive:true}).catch(()=>{});
  }
  function release(run) {
    clearTimeout(run.timer);
    if (run.stream) run.stream.getTracks().forEach(track => track.stop());
    run.stream = null;
    const video = document.getElementById('face-video');
    if (video) { video.pause(); video.srcObject = null; }
    patchContext.clearRect(0, 0, patchCanvas.width, patchCanvas.height);
  }
  function close() {
    if (!current) return;
    const old = current; current = null; sequence++;
    old.controller.abort(); release(old); old.profile = null; old.samples = [];
    const el = document.getElementById('face-screen');
    if (el) { el.hidden = true; el.classList.remove('face-photo-preview'); el.querySelector('#face-photo').removeAttribute('src'); }
    document.body.classList.remove('face-open');
    document.getElementById('shell').inert = false;
    document.getElementById('mobile-nav').inert = false;
    setMobileDrawer(false);
    if (old.returnFocus && old.returnFocus.isConnected) old.returnFocus.focus({ preventScroll: true });
  }
  function update(run, message, border = 'blue', progress = 0, hint = '') {
    if (!active(run)) return;
    const el = screen(); el.dataset.border = border;
    // Avoid announcing identical instructions on every camera frame.
    const status = el.querySelector('#face-status');
    if (status.textContent !== message) status.textContent = message;
    el.querySelector('#face-hint').textContent = hint;
    run.stage = message;
  }
  function fail(run, message) {
    if (!active(run)) return;
    diagnostic(run,run.phase || 'error',message,run.matchResult);
    run.finished = true; run.verifying = false; release(run);
    run.profile = null; run.samples = [];
    run.preview = false;
    screen().querySelector('#face-save-photo').hidden = true;
    screen().querySelector('#face-take-photo').hidden = true;
    screen().querySelector('#face-retake').hidden = true;
    update(run, message, 'error', 0);
    screen().querySelector('#face-retry').hidden = false;
    screen().querySelector('#face-done').hidden = false;
    // Invalidate in-flight inference/profile/GPS work before it can send an unlock.
    run.controller.abort();
  }
  function setup(deviceId, options = {}) {
    close(); setMobileDrawer(false);
    if (!state.user) { toast('Silakan masuk terlebih dahulu.', 'err'); return null; }
    const device = state.devices.find(d => d.id === deviceId);
    if (options.mode !== 'enroll' && !device) { toast('Perangkat tidak ditemukan.', 'err'); return null; }
    if (options.mode !== 'enroll' && state.user.role !== 'owner' && device.can_use_face !== true) { toast('Owner belum mengizinkan Face Unlock pada perangkat ini.', 'err'); return null; }
    const run = { id: ++sequence, deviceId, mode: options.mode || 'unlock', targetUser: options.targetUser, targetName: options.targetName,
      userId: state.user.id, token: state.token, controller: new AbortController(), samples: [],
      returnFocus: document.activeElement, stream: null, finished: false, verifying: false };
    current = run;
    const el = screen(); el.hidden = false;
    el.classList.remove('face-photo-preview');
    el.querySelector('#face-photo').hidden = true;
    el.querySelector('#face-photo').removeAttribute('src');
    el.querySelector('#face-device-label').textContent = run.mode === 'enroll' ? 'Daftar wajah · ' + run.targetName : device.name;
    el.querySelector('.face-simulation-badge').hidden = !device?.simulated;
    el.querySelector('.face-simulation-badge').textContent = 'SIMULASI · Smartlock virtual';
    el.querySelector('.face-oval').hidden = false;
    el.querySelector('.face-placeholder').hidden = false;
    el.querySelectorAll('.face-controls button').forEach(b => b.hidden = true);
    document.body.classList.add('face-open');
    document.getElementById('shell').inert = true;
    document.getElementById('mobile-nav').inert = true;
    el.querySelector('.face-back').focus();
    return run;
  }
  function loadModels() {
    if (modelPromise) return modelPromise;
    modelPromise = (async () => {
      if (!window.faceapi) await new Promise((resolve, reject) => {
        const script = document.createElement('script');
        const timeout = setTimeout(() => { script.remove(); reject(new Error('Model wajah belum dapat dimuat. Periksa koneksi internet lalu coba lagi.')); }, 30000);
        script.src = CDN + '/dist/face-api.js'; script.crossOrigin = 'anonymous';
        script.onload = () => { clearTimeout(timeout); resolve(); };
        script.onerror = () => { clearTimeout(timeout); script.remove(); reject(new Error('Library deteksi wajah gagal dimuat. Periksa koneksi internet.')); };
        document.head.append(script);
      });
      if (!window.faceapi) throw new Error('Library deteksi wajah tidak tersedia.');
      await faceapi.tf.ready();
      let timeout;
      try {
        await Promise.race([
          Promise.all([faceapi.nets.tinyFaceDetector.loadFromUri(CDN + '/model'), faceapi.nets.faceLandmark68Net.loadFromUri(CDN + '/model'), faceapi.nets.faceRecognitionNet.loadFromUri(CDN + '/model')]),
          new Promise((_, reject) => { timeout = setTimeout(() => reject(new Error('Unduhan model wajah terlalu lama. Periksa koneksi lalu coba lagi.')), 60000); }),
        ]);
      } finally { clearTimeout(timeout); }
    })().catch(error => { modelPromise = null; throw error; });
    return modelPromise;
  }
  async function open(deviceId, options = {}) {
    const run = setup(deviceId, options);
    if (!run) return;
    if (run.mode === 'enroll' && !options.consent) {
      update(run, 'Daftarkan wajah ' + run.targetName, 'blue', 0, 'Setelah kamera terbuka, tekan Ambil foto. Foto diperiksa satu kali; referensi numeriknya disimpan setelah konfirmasi. Foto/video tidak disimpan di server.');
      screen().querySelector('#face-consent').hidden = false;
      return;
    }
    begin(run);
  }
  async function begin(run) {
    update(run, 'Menyiapkan verifikasi wajah…', 'blue', 0, 'Izinkan kamera depan. Gunakan pencahayaan yang merata dan lepaskan penutup wajah.');
    try {
      if (!window.isSecureContext || !navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) throw new Error('Kamera memerlukan HTTPS atau localhost. Buka aplikasi melalui koneksi yang aman.');
      if (run.mode === 'unlock') {
        run.phase='gps';
        if (!run.token) throw new Error('Sesi login tidak tersedia. Silakan masuk kembali.');
        update(run, 'Mengambil lokasi untuk memeriksa radius…', 'blue', 0, 'Kamera baru diaktifkan setelah lokasi lolos geofence owner.');
        const position = await gps();
        if (!active(run)) return;
        const precheck = await api('/devices/' + encodeURIComponent(run.deviceId) + '/face-precheck', { method: 'POST', body: position, signal: run.controller.signal });
        if (!active(run)) return;
        run.threshold = precheck.face_match_threshold ?? .45;
        if (precheck.allowed !== true) throw new Error('Lokasi belum memenuhi radius yang diizinkan owner.');
        update(run, 'Lokasi sesuai. Menyiapkan identifikasi wajah…');
        run.profile = await api('/auth/me/face-profile', { signal: run.controller.signal });
        if (!active(run)) return;
        if (run.profile.model_version !== Core.MODEL || !Array.isArray(run.profile.descriptors) || ![1,3].includes(run.profile.descriptors.length) || !run.profile.descriptors.every(Core.validDescriptor) || run.profile.user_id && run.profile.user_id !== run.userId) throw new Error('Referensi wajah tidak valid. Daftarkan ulang wajah Anda.');
      }
      if (!active(run)) return;
      run.phase='camera';
      update(run, 'Mengaktifkan kamera depan…');
      const stream = await navigator.mediaDevices.getUserMedia({ audio: false, video: { facingMode: 'user', width: { ideal: 640 }, height: { ideal: 854 } } });
      if (!active(run)) { stream.getTracks().forEach(track => track.stop()); return; }
      run.stream = stream;
      const video = screen().querySelector('video'); video.srcObject = stream;
      stream.getVideoTracks().forEach(track => track.addEventListener('ended', () => { if (active(run) && !run.finished) fail(run, 'Kamera terputus. Izinkan akses kamera lalu coba lagi.'); }));
      await video.play();
      if (!active(run)) return;
      screen().querySelector('.face-placeholder').hidden = true;
      update(run, run.mode === 'enroll' ? 'Siap mengambil foto pendaftaran' : 'Ambil foto untuk akun ' + (run.profile?.user_name || state.user.name), 'blue', 0, 'Gunakan tempat yang terang. Hadapkan wajah ke kamera, pastikan mata, hidung, dan mulut terlihat jelas, lalu tekan Ambil foto.' + (run.mode === 'unlock' ? ' Batas pencocokan akun ini: '+run.threshold.toFixed(2)+'.' : ''));
      screen().querySelector('#face-take-photo').hidden = false;
    } catch (error) {
      const messages = { NotAllowedError: 'Izin kamera ditolak. Izinkan kamera di pengaturan browser lalu coba lagi.', NotFoundError: 'Kamera depan tidak ditemukan.', NotReadableError: 'Kamera sedang digunakan aplikasi lain. Tutup aplikasi tersebut lalu coba lagi.' };
      fail(run, messages[error.name] || error.message || 'Kamera tidak dapat diaktifkan.');
    }
  }
  function patchStats(canvas, x, y, width, height) {
    if (![x,y,width,height].every(Number.isFinite) || width < 2 || height < 2 || x < 0 || y < 0 || x + width > canvas.width || y + height > canvas.height) return { mean: 0, contrast: 0, sharpness: 0 };
    patchContext.drawImage(canvas, x, y, width, height, 0, 0, 64, 64);
    const data = patchContext.getImageData(0, 0, 64, 64).data;
    const gray = new Float32Array(4096);
    let sum = 0, sq = 0, lap = 0, lapSq = 0;
    for (let i = 0; i < gray.length; i++) { const j = i * 4; const v = .299 * data[j] + .587 * data[j+1] + .114 * data[j+2]; gray[i] = v; sum += v; sq += v*v; }
    for (let y = 1; y < 63; y++) for (let x = 1; x < 63; x++) { const i = y * 64 + x; const v = gray[i-1] + gray[i+1] + gray[i-64] + gray[i+64] - 4 * gray[i]; lap += v; lapSq += v*v; }
    return { mean: sum / 4096, contrast: Math.sqrt(Math.max(0, sq / 4096 - (sum / 4096) ** 2)), sharpness: lapSq / 3844 - (lap / 3844) ** 2 };
  }
  const dist = (a, b) => Math.hypot(a.x-b.x, a.y-b.y);
  const center = points => ({ x: points.reduce((s,p) => s+p.x,0)/points.length, y: points.reduce((s,p) => s+p.y,0)/points.length });
  function normalizeFace(result, canvas) {
    const box = result.detection.box, points = result.landmarks.positions;
    const oval = screen().querySelector('.face-oval');
    const scale = Math.max(oval.clientWidth / canvas.width, oval.clientHeight / canvas.height);
    const ox = (canvas.width * scale - oval.clientWidth) / 2, oy = (canvas.height * scale - oval.clientHeight) / 2;
    const normalizedBox = { x: (box.x*scale-ox)/oval.clientWidth, y: (box.y*scale-oy)/oval.clientHeight, width: box.width*scale/oval.clientWidth, height: box.height*scale/oval.clientHeight };
    if (!Array.isArray(points) || points.length !== 68 || !points.every(p => Number.isFinite(p.x) && Number.isFinite(p.y))) return { box: normalizedBox, landmarksVisible: false };
    const le = points.slice(36,42), re = points.slice(42,48), lc = center(le), rc = center(re), nose = points[30], mouth = center(points.slice(48,60));
    const eyeDistance = dist(lc, rc);
    const ear = e => (dist(e[1],e[5])+dist(e[2],e[4])) / (2 * dist(e[0],e[3]));
    const region = (c, w, h) => patchStats(canvas, c.x-w/2, c.y-h/2, w, h);
    const leftStats = region(lc, eyeDistance*.5, eyeDistance*.28), rightStats = region(rc, eyeDistance*.5, eyeDistance*.28);
    const noseStats = region(nose, eyeDistance*.25, eyeDistance*.25), mouthStats = region(mouth, eyeDistance*.8, eyeDistance*.35);
    const full = patchStats(canvas, box.x, box.y, box.width, box.height);
    const eyeY = (lc.y+rc.y)/2;
    const mainPoints = [...le,...re,points[30],...points.slice(48,68)];
    const mainInFrame = mainPoints.every(p=>p.x>=0 && p.y>=0 && p.x<=canvas.width && p.y<=canvas.height);
    const visible = mainInFrame && eyeDistance > 25 && nose.y > eyeY && mouth.y > nose.y;
    return { box: normalizedBox, score: result.detection.score, landmarksVisible: visible,
      source:{width:canvas.width,height:canvas.height,faceWidth:box.width,faceHeight:box.height},
      pose: { roll: Math.atan2(rc.y-lc.y,rc.x-lc.x)*180/Math.PI, yaw: (nose.x-(lc.x+rc.x)/2)/eyeDistance, pitch: (nose.y-eyeY)/(mouth.y-eyeY) },
      quality: { brightness: full.mean, sharpness: full.sharpness, eyesOpen: Math.min(ear(le),ear(re)), eyeTexture: Math.min(leftStats.contrast,rightStats.contrast), noseTexture: noseStats.contrast, mouthTexture: mouthStats.contrast } };
  }
  async function verifyPhoto(run, descriptor) {
    try {
      run.phase='identity';
      screen().querySelector('#face-retake').hidden = true;
      const initial = Core.compareIdentity(descriptor, run.profile, run.threshold);
      run.matchResult=initial;
      diagnostic(run,'identity',initial.matched?'Foto cocok':'Foto tidak cocok',initial);
      if (!initial.valid) throw new Error('Referensi atau threshold wajah tidak valid. Periksa pendaftaran wajah dan pengaturan owner.');
      if (!initial.matched) throw new Error('Pencocokan wajah ditolak: jarak ' + initial.distance.toFixed(3) + ', batas owner ' + initial.threshold.toFixed(2) + '. Jarak harus lebih kecil atau sama dengan batas. Batas 0.30 sangat ketat; default 0.45. Pastikan foto terdaftar milik akun ini.');
      update(run, 'Foto cocok. Memeriksa lokasi terbaru…', 'blue', 0);
      run.phase='gps';
      const position = await gps();
      if (!active(run)) return;
      const profile = await api('/auth/me/face-profile', { signal: run.controller.signal });
      if (!active(run)) return;
      const policy = await api('/devices/' + encodeURIComponent(run.deviceId) + '/face-precheck', { method: 'POST', body: position, signal: run.controller.signal });
      if (!active(run)) return;
      if (policy.allowed !== true || profile.user_id && profile.user_id !== run.userId) throw new Error('Akses Ditolak: Identitas atau kebijakan akses berubah. Ambil foto lagi.');
      const finalMatch = Core.compareIdentity(descriptor, profile, policy.face_match_threshold ?? .45);
      run.phase='identity';run.matchResult=finalMatch;
      if (!finalMatch.valid) throw new Error('Referensi atau threshold terbaru tidak valid. Periksa pengaturan owner.');
      if (!finalMatch.matched) throw new Error('Pencocokan terbaru ditolak: jarak ' + finalMatch.distance.toFixed(3) + ', batas owner ' + finalMatch.threshold.toFixed(2) + '. Referensi wajah atau threshold berubah. Ambil foto lagi.');
      run.verifiedName = profile.user_name || state.user.name;
      run.finished = true;
      await sendCommand(run, { face_verified: true, ...position });
    } catch(error) { fail(run, error.message); }
  }
  async function takePhoto(run) {
    if (!active(run) || run.verifying || run.preview) return;
    const video = screen().querySelector('video');
    if (video.readyState < 2 || !video.videoWidth || !run.stream?.active) return;
    run.verifying = true;
    run.phase='quality';
    screen().querySelector('#face-take-photo').hidden = true;
    const snapshot = document.createElement('canvas');
    snapshot.width = video.videoWidth; snapshot.height = video.videoHeight;
    run.photoMetrics={source:{width:snapshot.width,height:snapshot.height}};
    snapshot.getContext('2d').drawImage(video,0,0);
    const photo = screen().querySelector('#face-photo');
    photo.src = snapshot.toDataURL('image/jpeg',.85); photo.hidden = false;
    screen().classList.add('face-photo-preview');
    release(run);
    screen().querySelector('#face-retake').hidden = false;
    update(run,'Memeriksa foto Anda…','blue',0,'Foto sudah diambil. Pemeriksaan dilakukan pada foto ini saja.');
    try {
      await loadModels(); if(!active(run)) return;
      const faces = await faceapi.detectAllFaces(snapshot,new faceapi.TinyFaceDetectorOptions({inputSize:512,scoreThreshold:.35})).withFaceLandmarks().withFaceDescriptors();
      if(!active(run)) return;
      run.faceCount=faces.length;
      if(faces.length !== 1) throw new Error(faces.length ? 'Foto memuat lebih dari satu wajah. Ambil ulang dengan satu orang saja.' : 'Wajah belum terlihat pada foto. Silakan ambil ulang.');
      const sample=normalizeFace(faces[0],snapshot);run.photoMetrics=sample;
      const reason = Core.quality(sample, run.mode === 'unlock');
      diagnostic(run,'quality',reason || 'Geometri wajah dan resolusi foto memenuhi pemeriksaan');
      if(reason) throw new Error('Kualitas foto: ' + reason + '. Threshold pencocokan belum diperiksa.');
      if(!Core.validDescriptor(faces[0].descriptor)) throw new Error('Foto belum dapat dikenali. Silakan ambil ulang.');
      const descriptor = Array.from(faces[0].descriptor);
      if (run.mode === 'unlock') { await verifyPhoto(run, descriptor); return; }
      run.samples = [descriptor]; run.preview = true;
      update(run,'Gunakan foto wajah ini?','blue',0,'Foto hanya untuk pratinjau. Referensi wajah disimpan setelah Anda menekan Gunakan foto ini.');
      screen().querySelector('#face-save-photo').hidden = false;
    } catch(error) { if(active(run)){diagnostic(run,run.phase || 'error',error.message,run.matchResult);update(run,error.message,'warning',0,'Tekan Ambil ulang untuk mengambil foto baru. Versi '+Core.CLIENT_VERSION);} }
    finally { snapshot.width=0; snapshot.height=0; run.verifying=false; }
  }
  async function saveEnrollment(run) {
    if (!active(run) || !run.preview || run.saving) return;
    run.saving = true;
    const button = screen().querySelector('#face-save-photo'); button.disabled = true;
    screen().querySelector('#face-retake').hidden = true;
    try {
      const endpoint = state.user.role === 'owner' ? '/auth/users/' + encodeURIComponent(run.targetUser) + '/face-profile' : '/auth/me/face-profile';
      await api(endpoint, { method: 'PUT', body: { descriptors: run.samples, model_version: Core.MODEL }, signal: run.controller.signal });
      if (!active(run)) return;
      document.dispatchEvent(new CustomEvent('smartlock:face-registered', { detail: { userId: run.targetUser } }));
      run.samples = []; run.finished = true; run.preview = false;
      button.hidden = true;
      update(run, 'Foto wajah berhasil didaftarkan', 'success', 10, 'Wajah Anda siap digunakan untuk Face Unlock.');
      screen().querySelector('#face-done').hidden = false;
    } catch(error) { fail(run, error.message); button.hidden = true; }
    finally { button.disabled = false; run.saving = false; }
  }
  function gps() {
    return new Promise((resolve, reject) => {
      if (!navigator.geolocation) { reject(new Error('Browser tidak mendukung lokasi GPS.')); return; }
      navigator.geolocation.getCurrentPosition(pos => {
        const { latitude, longitude, accuracy } = pos.coords;
        if (![latitude,longitude,accuracy].every(Number.isFinite) || Math.abs(latitude)>90 || Math.abs(longitude)>180 || accuracy<0 || Date.now()-pos.timestamp>15000) { reject(new Error('Lokasi GPS tidak valid atau sudah kedaluwarsa. Coba lagi.')); return; }
        resolve({ latitude, longitude, accuracy_m: accuracy });
      }, error => reject(new Error(error.code === 1 ? 'Izin lokasi ditolak. Izinkan lokasi untuk membuka pintu.' : error.code === 3 ? 'Lokasi GPS belum diperoleh. Coba lagi di tempat terbuka.' : 'Lokasi GPS tidak tersedia. Periksa pengaturan lokasi perangkat.')), { enableHighAccuracy: true, maximumAge: 0, timeout: 15000 });
    });
  }
  async function sendCommand(run, body) {
    if (!active(run) || !run.token) throw new Error('Masuk dengan akun asli untuk membuka pintu.');
    update(run, 'Wajah dikenali: ' + run.verifiedName, 'blue', 10, 'Mengirim perintah buka smartlock…');
    const result = await api('/devices/' + encodeURIComponent(run.deviceId) + '/unlock', { method: 'POST', body, signal: run.controller.signal });
    if (!active(run)) return;
    if (result.status !== 'command_sent' || !result.transaction_id) throw new Error('Backend belum mengonfirmasi pengiriman perintah. Jangan mengirim ulang sebelum memeriksa status.');
    update(run, 'Perintah buka pintu terkirim, membuka kunci…', 'success', 10, 'Wajah terverifikasi: ' + run.verifiedName + '. Menunggu konfirmasi perangkat.');
    run.transactionId = result.transaction_id; run.pollStarted = performance.now();
    poll(run);
  }
  async function poll(run) {
    if (!active(run)) return;
    try {
      const base = '/devices/' + encodeURIComponent(run.deviceId);
      const [command, device] = await Promise.all([api(base + '/commands/' + encodeURIComponent(run.transactionId), { signal: run.controller.signal }), api(base, { signal: run.controller.signal })]);
      if (!active(run)) return;
      const index = state.devices.findIndex(d => d.id === device.id);
      if (index >= 0) state.devices[index] = device;
      if (command.result === 'success') {
        diagnostic(run,'success','ACK smartlock diterima',run.matchResult);
        const simulated = command.simulated === true || device.simulated === true;
        update(run, simulated ? 'Smartlock berhasil dibuka — Simulasi' : 'Perangkat mengonfirmasi perintah buka kunci', 'success', 10, 'Wajah terverifikasi: ' + run.verifiedName + '. ' + (simulated ? 'Perangkat virtual menerima perintah. Tidak ada pintu fisik yang dibuka.' : 'Status pintu: ' + (device.door_state === 'open' ? 'terbuka' : 'tertutup') + '.'));
        toast((simulated ? 'Simulasi: ' : '') + run.verifiedName + ', smartlock berhasil dibuka.', 'ok');
        screen().querySelector('#face-done').hidden = false; return;
      }
      if (['failed','denied','timeout'].includes(command.result)) { fail(run, 'Perangkat menolak atau gagal menjalankan perintah buka kunci.'); return; }
      if (performance.now() - run.pollStarted >= 20000) {
        update(run, 'Perintah terkirim, konfirmasi belum diterima', 'warning', 10, 'Periksa kondisi pintu atau riwayat akses. Aplikasi tidak mengirim ulang perintah secara otomatis.');
        screen().querySelector('#face-done').hidden = false; return;
      }
      run.timer = setTimeout(() => poll(run), 1000);
    } catch (error) {
      if (active(run)) { update(run, 'Perintah sudah terkirim. Status belum dapat diperiksa', 'warning', 10, error.message); screen().querySelector('#face-done').hidden = false; }
    }
  }
  function register() {
    const device = state.devices.find(d => d.id === state.selectedDeviceId) || state.devices[0];
    if (!state.user || (state.user.role !== 'owner' && (!device || device.can_use_face !== true))) {
      toast('Owner belum mengizinkan pendaftaran wajah pada perangkat Anda.', 'err');
      return;
    }
    open(null, { mode: 'enroll', targetUser: state.user.id, targetName: state.user.name });
  }
  async function populateUsers() {
    const select = document.getElementById('face-enroll-user');
    if (!select) return;
    try {
      const users = await api('/auth/users');
      if (!select.isConnected) return;
      select.replaceChildren();
      users.filter(u => u.is_active).forEach(u => { const option = document.createElement('option'); option.value = u.id; option.textContent = u.name + ' · ' + u.email; option.selected = u.id === state.user.id; select.append(option); });
    } catch (error) { select.replaceChildren(new Option(error.message, '')); }
  }
  function enroll() {
    if (!state.user || state.user.role !== 'owner') { toast('Pendaftaran wajah hanya dapat dilakukan owner.', 'err'); return; }
    const select = document.getElementById('face-enroll-user');
    if (!select || !select.value) { toast('Pilih akun yang akan didaftarkan.', 'err'); return; }
    open(null, { mode: 'enroll', targetUser: select.value, targetName: select.selectedOptions[0].textContent });
  }
  async function removeProfile() {
    const select = document.getElementById('face-enroll-user');
    if (!select || !select.value) return;
    if (!await confirmDialog('Hapus referensi wajah?', 'Akun ini tidak dapat menggunakan Face Unlock hingga didaftarkan kembali.')) return;
    try { await api('/auth/users/' + encodeURIComponent(select.value) + '/face-profile', { method: 'DELETE' }); toast('Referensi wajah dihapus.', 'ok'); } catch (error) { toast(error.message, 'err'); }
  }
  function pause(run) { if (active(run) && !run.finished) fail(run, 'Verifikasi dijeda. Kembali ke posisi portrait dan pilih Coba Lagi.'); }
  document.addEventListener('visibilitychange', () => { if (document.hidden && current) pause(current); });
  new MutationObserver(() => { if (document.body.classList.contains('portrait-blocked') && current) pause(current); }).observe(document.body, { attributes: true, attributeFilter: ['class'] });
  addEventListener('pagehide', close);
  window.FaceUnlock = { open, close, register, enroll, removeProfile, populateUsers };
})();
