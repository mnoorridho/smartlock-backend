/* User-facing presentation. Device/method authorization remains in the API. */
(function () {
  'use strict';
  let historyView = null;
  let faceStatusRevision = 0;
  const e = value => escapeHtml(String(value ?? ''));
  const icons = {
    face: '<path d="M8 3H3v5m13-5h5v5M3 16v5h5m13-5v5h-5M8 9h1m6 0h1m-5 1v4h2m-5 2c2 2 6 2 8 0"/>',
    nfc: '<rect x="3" y="5" width="18" height="14" rx="3"/><path d="M7 10h4m-4 4h2m6-5c2 2 2 4 0 6m3-8c3 3 3 7 0 10"/>',
    quick: '<path d="m13 2-9 12h7l-1 8 10-13h-7z"/>',
    pin: '<path d="M19 10c0 5-7 11-7 11S5 15 5 10a7 7 0 1 1 14 0Z"/><circle cx="12" cy="10" r="2"/>',
    clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    shield: '<path d="m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6z"/><path d="m8 12 3 3 5-6"/>',
    refresh: '<path d="M20 7v5h-5M4 17v-5h5M6 7a7 7 0 0 1 12-2l2 3M4 16l2 3a7 7 0 0 0 12-2"/>',
    user: '<circle cx="12" cy="8" r="4"/><path d="M4 21v-2a8 8 0 0 1 16 0v2"/>',
    arrow: '<path d="M5 12h14m-5-5 5 5-5 5"/>',
    lock: '<rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/>',
    check: '<path d="m5 12 4 4L19 6"/>',
  };
  const icon = name => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${icons[name] || icons.shield}</svg>`;
  const schedule = d => d.access_window_enabled === false ? 'Sesuai izin akun' : `${String(d.access_start_time || '07:00').slice(0,5)}–${String(d.access_end_time || '17:00').slice(0,5)} WIB`;
  function header(title, text, action = '') {
    return `<div class="overview-header user-page-heading"><div><div class="eyebrow">SMART ACCESS · AKUN PENGGUNA</div><h2>${e(title)}</h2><p>${e(text)}</p></div>${action}</div>`;
  }
  const refreshButton = () => `<button type="button" class="btn btn-ghost user-refresh" onclick="UserPortal.refreshDevices(this)">${icon('refresh')} Perbarui akses</button>`;
  function empty(title, text, action = '') {
    return `<div class="user-empty">${icon('shield')}<h3>${e(title)}</h3><p>${e(text)}</p>${action}</div>`;
  }
  function context(id, deviceId) {
    const node = document.getElementById(id), userId = state.user.id, token = state.token;
    return () => document.getElementById(id) === node && state.user?.id === userId && state.token === token && (!deviceId || state.selectedDeviceId === deviceId);
  }
  function noDevices() {
    setContent(`<div class="user-portal">${header('Akses Smartlock Saya', 'Perangkat dan metode akses mengikuti persetujuan owner.', refreshButton())}<div class="panel">${empty('Belum ada perangkat yang disetujui', 'Minta owner menambahkan akun Anda ke perangkatnya. Setelah disetujui, perangkat dan metode akses akan muncul di sini.', '<button class="btn btn-ghost" onclick="UserPortal.refreshDevices(this)">Periksa lagi</button>')}</div><div class="overview-note"><span class="note-icon">i</span><p>Anda tidak perlu menambahkan perangkat sendiri. Owner mengatur persetujuan, metode akses, dan jadwal penggunaan Anda.</p></div></div>`);
  }
  function pills(d) {
    return `<div class="verif-row">${[['face','Wajah'],['nfc','NFC'],['quick','Quick']].map(([key,label]) => `<span class="pill ${d['can_use_'+key] === true ? 'badge-on' : 'badge-off'}">${e(label)}</span>`).join('')}</div>`;
  }
  function methods(d) {
    const items = [
      ['face','Buka dengan wajah','Periksa radius lokasi, lalu identifikasi wajah', `FaceUnlock.open('${d.id}')`],
      ['nfc','Buka dengan kartu NFC','Gunakan kartu yang terdaftar pada akun Anda', "goTo('nfc')"],
      ['quick','Quick access','Buka langsung sesuai persetujuan owner', "unlockMyDevice('quick',null,this)"],
    ];
    return `<div class="user-methods">${items.map(([key,label,description,action]) => {
      const allowed = d['can_use_'+key] === true;
      return `<button type="button" class="access-action user-method" ${allowed ? `onclick="${action}"` : 'disabled'} title="${allowed ? 'Diizinkan owner' : 'Tidak diizinkan owner'}"><span class="user-action-symbol ${key}">${icon(key)}</span><span class="user-action-copy"><strong>${label}</strong><small>${allowed ? description : 'Tidak diizinkan oleh owner'}</small></span><span class="user-action-arrow">${icon(allowed ? 'arrow' : 'lock')}</span></button>`;
    }).join('')}</div>`;
  }
  function hero(d) {
    return `<article class="overview-feature user-feature"><div class="feature-top"><div><span class="feature-label">PERANGKAT PILIHAN</span><h3>${e(d.name)}</h3><p>${e(d.location || 'Lokasi belum diberi label')} · ${e(d.device_code)}</p></div><span class="status-chip"><i class="dot ${isOnline(d) ? 'on' : 'off'}"></i>${isOnline(d) ? 'Terhubung' : 'Offline'}</span></div><div class="user-owner-line"><span class="user-small-avatar">${e((d.owner_name || 'O').slice(0,1).toUpperCase())}</span><span>Akses diberikan oleh <strong>${e(d.owner_name || 'Owner perangkat')}</strong></span></div><div class="feature-access-row"><div class="lock-visual"><div class="lock-visual-circle">${iconLock()}</div><div><span>Status kunci</span><strong>${e(d.lock_status || 'unknown')}</strong><small>Pintu fisik: ${e(d.door_state || 'unknown')}</small></div></div>${methods(d)}</div><div class="feature-footer"><div><span>JADWAL PERANGKAT</span><strong>${e(schedule(d))}</strong><small>Jadwal personal dan izin akun tetap diperiksa saat membuka.</small></div><button type="button" class="btn btn-ghost btn-sm" onclick="goTo('logs')">${icon('clock')} Riwayat saya</button></div></article>`;
  }
  function policy(d) {
    const row = (color,label,text) => `<div class="policy-row"><span class="policy-dot ${color}-dot"></span><div><strong>${e(label)}</strong><small>${e(text)}</small></div></div>`;
    return `<div class="overview-side"><div class="panel overview-side-panel user-policy"><div class="side-title-row"><div><div class="eyebrow">BATAS AKSES SAYA</div><h3>Izin dari owner</h3></div><span class="policy-mark">${icon('shield')}</span></div>${row('violet','Verifikasi wajah', d.can_use_face ? 'Diizinkan · lokasi diperiksa lebih dulu' : 'Belum diizinkan owner')}${row('amber','Kartu NFC',d.can_use_nfc ? 'Diizinkan untuk kartu akun Anda' : 'Belum diizinkan owner')}${row('mint','Quick access',d.can_use_quick ? 'Diizinkan owner' : 'Tidak diizinkan · tombol dinonaktifkan')}${row('green','Geofence wajah',d.latitude != null && d.longitude != null ? `Radius ${Math.round(d.geofence_radius_m || 0)} meter dari perangkat` : 'Lokasi belum diatur owner')}<div class="user-policy-footer">${icon('lock')}<span>Hanya owner yang dapat mengubah metode, radius, dan jadwal akses.</span></div></div><div class="overview-note"><span class="note-icon">i</span><p><strong>Mengapa tombol berwarna abu-abu?</strong><br>Metode tersebut belum disetujui atau sedang dinonaktifkan owner. Hubungi owner perangkat jika membutuhkan akses tambahan.</p></div></div>`;
  }
  function deviceCards(d) {
    return state.devices.map(dev => `<button type="button" class="overview-device-card ${dev.id === d.id ? 'selected' : ''}" aria-pressed="${dev.id === d.id}" onclick="chooseMyDevice('${dev.id}')"><div class="overview-device-top"><span class="device-glyph">${iconDoor()}</span><span class="status-chip"><i class="dot ${isOnline(dev) ? 'on' : 'off'}"></i>${isOnline(dev) ? 'Online' : 'Offline'}</span></div><div class="overview-device-name">${e(dev.name)}</div><div class="overview-device-code">${e(dev.device_code)}</div><p class="user-card-owner">Owner: ${e(dev.owner_name || 'Owner perangkat')}</p><div class="overview-device-state"><span>${iconLock()} ${e(dev.lock_status || 'unknown')}</span><span>${iconDoor()} ${e(dev.door_state || 'unknown')}</span></div><div class="overview-device-window">${e(schedule(dev))}</div>${pills(dev)}</button>`).join('');
  }
  function registrations(d) {
    return `<div class="user-registration-grid"><article class="panel user-registration-card"><span class="user-registration-symbol face">${icon('face')}</span><div class="user-registration-copy"><div class="user-card-heading"><h3>Wajah saya</h3><span class="user-state-pill" data-face-status>${d.can_use_face ? 'Memeriksa status…' : 'Belum diizinkan'}</span></div><p>Daftarkan wajah akun Anda agar dapat dikenali saat menggunakan Face Unlock.</p><div class="user-mini-steps"><span>01 · Buka kamera</span><span>02 · Ambil foto</span><span>03 · Konfirmasi foto</span></div><button type="button" class="btn btn-primary user-register-face" ${d.can_use_face === true ? 'onclick="FaceUnlock.register()"' : 'disabled'}>Daftar wajah ${icon('arrow')}</button></div></article><article class="panel user-registration-card"><span class="user-registration-symbol nfc">${icon('nfc')}</span><div class="user-registration-copy"><div class="user-card-heading"><h3>Kartu NFC saya</h3><span class="user-state-pill" data-nfc-status>${d.can_use_nfc ? 'Memuat kartu…' : 'Belum diizinkan'}</span></div><p>Kartu terhubung ke akun Anda dan hanya digunakan pada perangkat yang disetujui.</p><div class="user-mini-steps"><span>01 · Siapkan UID kartu</span><span>02 · Daftarkan ke akun</span><span>03 · Gunakan akses NFC</span></div><button type="button" class="btn btn-ghost" ${d.can_use_nfc === true ? "onclick=\"goTo('nfc')\"" : 'disabled'}>Daftar kartu NFC ${icon('arrow')}</button></div></article></div>`;
  }
  function metric(symbol,color,label,value,detail,id='') {
    return `<div class="overview-metric"><div class="metric-symbol ${color}">${icon(symbol)}</div><div><span>${label}</span><strong ${id ? `id="${id}"` : ''}>${value}</strong><small>${detail}</small></div></div>`;
  }
  function faceStatus(root, registered, allowed) {
    root.querySelectorAll('[data-face-status]').forEach(el => { el.textContent = !allowed ? 'Belum diizinkan' : registered === true ? 'Terdaftar' : registered === false ? 'Belum terdaftar' : 'Status belum tersedia'; el.classList.toggle('ready', allowed && registered === true); });
    root.querySelectorAll('.user-register-face').forEach(el => { el.innerHTML = `${registered === true ? 'Perbarui wajah' : 'Daftar wajah'} ${icon('arrow')}`; });
  }
  async function hydrate(rootId,d) {
    const valid = context(rootId,d.id), root=document.getElementById(rootId);
    const revision = faceStatusRevision;
    const results=await Promise.allSettled([
      d.can_use_face ? api('/auth/me/face-profile/status') : Promise.resolve(null),
      d.can_use_nfc ? api('/nfc-cards/?device_id='+encodeURIComponent(d.id)) : Promise.resolve(null),
      root.querySelector('[data-recent-history]') ? api('/devices/'+encodeURIComponent(d.id)+'/logs') : Promise.resolve(null),
    ]);
    if(!valid())return;
    const [face,cards,logs]=results;
    if(revision===faceStatusRevision)faceStatus(root,face.status==='fulfilled'?face.value?.registered:undefined,d.can_use_face===true);
    const list=cards.status==='fulfilled' && Array.isArray(cards.value)?cards.value:null;
    root.querySelectorAll('[data-nfc-status]').forEach(el=>{el.textContent=!d.can_use_nfc?'Belum diizinkan':list?`${list.length} kartu terdaftar`:'Status belum tersedia';el.classList.toggle('ready',!!list?.some(c=>c.is_active));});
    const count=root.querySelector('#user-active-cards');if(count)count.textContent=list?String(list.filter(c=>c.is_active).length):'—';
    const recent=root.querySelector('[data-recent-history]');
    if(recent){const records=logs.status==='fulfilled'&&Array.isArray(logs.value)?logs.value.filter(l=>l.user_id===state.user.id):null;recent.innerHTML=records?records.length?timeline(records.slice(0,3)):empty('Belum ada aktivitas','Riwayat Anda akan muncul setelah menggunakan perangkat.'):empty('Riwayat belum tersedia','Periksa koneksi atau perbarui hak akses Anda.','<button class="btn btn-ghost" onclick="goTo(\'logs\')">Coba lihat riwayat</button>');}
  }
  function renderHome() {
    const d=mySelectedDevice();if(!d){noDevices();return;}
    const methodsCount=['face','nfc','quick'].filter(k=>d['can_use_'+k]===true).length;
    setContent(`<div id="user-home" class="user-portal">${header('Akses Smartlock Saya',`Halo, ${state.user.name}. Gunakan akses Anda dengan aman dan mudah.`,refreshButton())}<div class="overview-metrics">${metric('lock','mint','Perangkat saya',state.devices.length,'Disetujui oleh owner')}${metric('shield','green','Perangkat online',state.devices.filter(isOnline).length,'Status koneksi terakhir')}${metric('face','violet','Metode diizinkan',`${methodsCount}<em> / 3</em>`,'Untuk perangkat pilihan')}${metric('nfc','amber','Kartu NFC aktif','—','Milik Anda di perangkat ini','user-active-cards')}</div><div class="user-toolbar">${myDevicePicker(d)}<span class="user-account-tag">${icon('user')} Akun pengguna</span></div><div class="overview-main-grid user-main-grid">${hero(d)}${policy(d)}</div><div class="overview-section-title"><div><h3>Pendaftaran saya</h3><p>Siapkan identitas dan kartu untuk metode yang sudah disetujui.</p></div></div>${registrations(d)}<div class="user-lower-grid"><section class="panel user-recent-panel"><div class="user-section-heading"><div><div class="eyebrow">AKTIVITAS TERBARU</div><h3>Riwayat akses saya</h3></div><button class="btn btn-ghost btn-sm" onclick="goTo('logs')">Lihat semua ${icon('arrow')}</button></div><div data-recent-history>${loadingHtml('Memuat aktivitas Anda…')}</div></section><aside class="panel user-flow-panel"><div class="eyebrow">FACE UNLOCK</div><h3>Langkah membuka pintu</h3><ol class="user-flow"><li><b>1</b><div><strong>Berada di sekitar perangkat</strong><p>Lokasi diperiksa sesuai radius owner.</p></div></li><li><b>2</b><div><strong>Verifikasi wajah Anda</strong><p>Kamera aktif setelah pemeriksaan lokasi lolos.</p></div></li><li><b>3</b><div><strong>Tunggu konfirmasi smartlock</strong><p>Hasil perintah muncul setelah diproses perangkat.</p></div></li></ol></aside></div><div class="overview-section-title"><div><h3>Perangkat saya</h3><p>Pilih perangkat lain untuk melihat metode aksesnya.</p></div><button class="btn btn-ghost btn-sm" onclick="goTo('devices')">Lihat perangkat ${icon('arrow')}</button></div><div class="overview-device-grid">${deviceCards(d)}</div></div>`);
    hydrate('user-home',d);
  }
  function renderDevices(){
    const d=mySelectedDevice();if(!d){noDevices();return;}
    setContent(`<div id="user-devices" class="user-portal">${header('Perangkat Saya','Lihat status dan gunakan perangkat yang telah disetujui owner.',refreshButton())}<div class="two-col user-devices-layout"><aside class="panel user-device-list"><div class="user-section-heading"><h3>Akses perangkat</h3><span class="user-state-pill">${state.devices.length} perangkat</span></div>${state.devices.map(dev=>`<button type="button" class="user-device-choice ${dev.id===d.id?'selected':''}" aria-pressed="${dev.id===d.id}" onclick="chooseMyDevice('${dev.id}')"><span class="device-glyph">${icon('lock')}</span><span><strong>${e(dev.name)}</strong><small>${e(dev.owner_name||'Owner perangkat')}</small><span class="user-list-connection"><i class="dot ${isOnline(dev)?'on':'off'}"></i>${isOnline(dev)?'Online':'Offline'}</span></span></button>`).join('')}<p class="hint">Perangkat baru hanya muncul setelah owner memberi Anda izin.</p></aside><div>${hero(d)}<div class="user-device-policy">${policy(d)}</div></div></div></div>`);
  }
  async function refreshDevices(button){
    const uid=state.user?.id,token=state.token;if(!uid)return;
    if(button){button.disabled=true;button.setAttribute('aria-busy','true');}
    try{const devices=await api('/devices/');if(state.user?.id!==uid||state.token!==token)return;if(!Array.isArray(devices))throw new Error('Daftar perangkat belum dapat diperbarui.');state.devices=devices;mySelectedDevice();if(state.currentPage==='devices')renderDevices();else if(state.currentPage==='nfc')renderNfc();else if(state.currentPage==='overview')renderHome();toast('Hak akses dan status perangkat diperbarui.','ok');}
    catch(error){if(state.user?.id===uid)toast(error.message,'err');}
    finally{if(button?.isConnected){button.disabled=false;button.removeAttribute('aria-busy');}}
  }
  async function renderNfc(){
    const d=mySelectedDevice();if(!d){noDevices();return;}
    if(d.can_use_nfc!==true){setContent(`<div class="user-portal">${header('Kartu NFC Saya','Pendaftaran kartu mengikuti izin perangkat Anda.')}${myDevicePicker(d)}<div class="panel">${empty('NFC belum diizinkan','Owner belum mengizinkan metode NFC pada perangkat ini. Anda dapat memilih perangkat lain atau menghubungi owner.','<button class="btn btn-ghost" onclick="goTo(\'overview\')">Kembali ke beranda</button>')}</div></div>`);return;}
    setContent(`<div id="user-nfc" class="user-portal">${header('Kartu NFC Saya','Daftarkan kartu atas akun Anda untuk perangkat yang disetujui.',refreshButton())}<div class="user-toolbar">${myDevicePicker(d)}<span class="user-account-tag">${icon('shield')} Owner: ${e(d.owner_name||'Owner perangkat')}</span></div><div class="user-compact-metrics">${metric('nfc','amber','Kartu terdaftar','—','Pada perangkat pilihan','my-nfc-total')}${metric('check','green','Kartu aktif','—','Siap digunakan','my-nfc-active')}${metric('lock','mint','Perangkat pilihan',e(d.name),'Kartu mengikuti izin perangkat')}</div><div class="user-lower-grid user-nfc-intro"><section class="panel"><div class="user-section-heading"><div><div class="eyebrow">PENDAFTARAN KARTU</div><h3>Tambahkan kartu saya</h3></div><span class="user-registration-symbol nfc">${icon('nfc')}</span></div><p class="user-section-copy">Kartu akan terhubung ke akun Anda pada ${e(d.name)}.</p><div class="form-row"><div class="form-field"><label for="my-nfc-label">Nama kartu</label><input id="my-nfc-label" maxlength="100" placeholder="Contoh: Kartu utama saya" autocomplete="off"><p class="hint">Nama membantu Anda mengenali kartu.</p></div><div class="form-field"><label for="my-nfc-uid">UID kartu NFC</label><input id="my-nfc-uid" maxlength="64" placeholder="04:A3:B2:C1" autocomplete="off"><p class="hint">Masukkan UID yang dibaca dari kartu/reader.</p></div></div><p id="my-nfc-feedback" class="user-inline-feedback" role="alert" hidden></p><button type="button" id="my-nfc-register" class="btn btn-primary" onclick="registerMyNfc()">${icon('nfc')} Daftarkan kartu saya</button></section><aside class="panel user-flow-panel"><div class="eyebrow">SEBELUM MENDAFTAR</div><h3>Siapkan kartu Anda</h3><ol class="user-flow"><li><b>1</b><div><strong>Gunakan kartu milik sendiri</strong><p>Pastikan UID berasal dari kartu/reader Anda.</p></div></li><li><b>2</b><div><strong>Pilih perangkat yang benar</strong><p>Pendaftaran berlaku pada perangkat pilihan.</p></div></li><li><b>3</b><div><strong>Periksa status kartu</strong><p>Kartu yang dinonaktifkan owner tidak dapat dipakai.</p></div></li></ol><div class="user-policy-footer">${icon('shield')} Pendaftaran kartu tidak membuka pintu.</div></aside></div><div class="overview-section-title"><div><h3>Daftar kartu saya</h3><p>Hanya kartu akun Anda pada perangkat ini.</p></div></div><div id="my-nfc-list">${loadingHtml('Memuat kartu saya…')}</div></div>`);
    const valid=context('user-nfc',d.id);
    try{const cards=await api('/nfc-cards/?device_id='+encodeURIComponent(d.id));if(!valid())return;if(!Array.isArray(cards))throw new Error('Daftar kartu belum tersedia.');document.getElementById('my-nfc-total').textContent=String(cards.length);document.getElementById('my-nfc-active').textContent=String(cards.filter(c=>c.is_active).length);document.getElementById('my-nfc-list').innerHTML=cards.length?`<div class="user-nfc-card-grid">${cards.map(card=>`<article class="user-nfc-card ${card.is_active?'':'inactive'}"><div class="user-nfc-card-top"><span>${icon('nfc')} SMARTLOCK ACCESS</span><span class="user-state-pill ${card.is_active?'ready':''}">${card.is_active?'Aktif':'Dinonaktifkan'}</span></div><h3>${e(card.label)}</h3><div class="user-nfc-uid">${e(card.card_uid)}</div><div class="user-nfc-card-bottom"><span>${e(d.name)}<small>Milik ${e(state.user.name)}</small></span><button type="button" class="btn btn-ghost" data-card-uid="${e(card.card_uid)}" ${card.is_active?'onclick="unlockMyDevice(\'nfc\',this.dataset.cardUid,this)"':'disabled'}>${icon('lock')} Gunakan kartu</button></div>${!card.is_active?'<p class="hint">Hubungi owner jika kartu ini perlu diaktifkan kembali.</p>':''}</article>`).join('')}</div>`:empty('Belum ada kartu terdaftar','Isi nama dan UID kartu di atas untuk menyiapkan akses NFC Anda.','<button class="btn btn-ghost" onclick="document.getElementById(\'my-nfc-label\').focus()">Daftarkan kartu pertama</button>');}
    catch(error){if(valid())document.getElementById('my-nfc-list').innerHTML=empty('Kartu belum dapat dimuat',error.message,'<button class="btn btn-ghost" onclick="UserPortal.renderNfc()">Coba lagi</button>');}
  }
  async function registerNfc(){
    const d=mySelectedDevice(),button=document.getElementById('my-nfc-register'),feedback=document.getElementById('my-nfc-feedback');
    if(!d||d.can_use_nfc!==true||!button||button.disabled)return;
    const label=document.getElementById('my-nfc-label').value.trim(),uid=document.getElementById('my-nfc-uid').value.trim();
    const problem=!label?'Isi nama kartu Anda.':!/^[A-Za-z0-9:_-]{1,64}$/.test(uid)?'Isi UID kartu yang valid, misalnya 04:A3:B2:C1.':null;
    if(problem){feedback.hidden=false;feedback.textContent=problem;document.getElementById(!label?'my-nfc-label':'my-nfc-uid').focus();return;}
    feedback.hidden=true;button.disabled=true;button.textContent='Mendaftarkan kartu…';
    const valid=context('user-nfc',d.id);
    try{await api('/nfc-cards/',{method:'POST',body:{device_id:d.id,card_uid:uid,label}});if(valid()){toast('Kartu Anda berhasil didaftarkan.','ok');renderNfc();}}
    catch(error){if(valid()){feedback.hidden=false;feedback.textContent=error.message;}}
    finally{if(button.isConnected){button.disabled=false;button.innerHTML=icon('nfc')+' Daftarkan kartu saya';}}
  }
  const methodName = name => ({face:'Verifikasi wajah',nfc:'Kartu NFC',manual:'Akses akun',qr:'Akses QR'}[name]||'Akses perangkat');
  function resultPill(result){const label={success:'Berhasil',denied:'Ditolak',failed:'Gagal',pending:'Menunggu',timeout:'Waktu habis'}[result]||'Status tersedia';return `<span class="user-result ${['success','denied','failed','pending','timeout'].includes(result)?result:''}">${label}</span>`;}
  function timeline(records){return `<div class="user-timeline">${records.map(log=>`<article class="user-timeline-item"><span class="user-timeline-icon ${log.result==='success'?'success':''}">${icon(log.method==='face'?'face':log.method==='nfc'?'nfc':'clock')}</span><div class="user-timeline-copy"><div><strong>${e(methodName(log.method))}</strong>${resultPill(log.result)}</div><p>${e(log.note||'Aktivitas akses perangkat Anda.')}</p><time>${e(fmtTime(log.timestamp))}</time></div></article>`).join('')}</div>`;}
  async function renderHistory(){
    const d=mySelectedDevice();if(!d){noDevices();return;}
    historyView=null;
    setContent(`<div id="user-history" class="user-portal">${header('Riwayat Akses Saya','Pantau hasil penggunaan perangkat Anda, tanpa aktivitas pengguna lain.','<button class="btn btn-ghost user-refresh" onclick="UserPortal.renderHistory()">'+icon('refresh')+' Muat ulang</button>')}<div class="user-toolbar">${myDevicePicker(d)}<span class="user-account-tag">${icon('lock')} Riwayat pribadi</span></div><div class="user-compact-metrics">${metric('clock','mint','Catatan ditampilkan','—','Aktivitas terbaru','my-history-total')}${metric('check','green','Berhasil','—','Dalam catatan ditampilkan','my-history-success')}${metric('shield','amber','Ditolak / gagal','—','Dalam catatan ditampilkan','my-history-failed')}</div><section class="panel user-history-panel"><div class="user-section-heading"><div><div class="eyebrow">AKTIVITAS PERANGKAT</div><h3>${e(d.name)}</h3></div><span class="user-state-pill">Owner: ${e(d.owner_name||'Owner perangkat')}</span></div><div class="user-history-filters"><div class="form-field"><label for="my-history-method">Metode akses</label><select id="my-history-method" onchange="UserPortal.filterHistory()"><option value="">Semua metode</option><option value="face">Wajah</option><option value="nfc">NFC</option><option value="manual">Akses akun</option></select></div><div class="form-field"><label for="my-history-result">Hasil akses</label><select id="my-history-result" onchange="UserPortal.filterHistory()"><option value="">Semua hasil</option><option value="success">Berhasil</option><option value="denied">Ditolak</option><option value="failed">Gagal</option><option value="pending">Menunggu</option><option value="timeout">Waktu habis</option></select></div></div><div id="my-history-list">${loadingHtml('Memuat riwayat akses Anda…')}</div><p class="hint" id="my-history-caption"></p></section></div>`);
    const valid=context('user-history',d.id);
    try{const records=await api('/devices/'+encodeURIComponent(d.id)+'/logs');if(!valid())return;if(!Array.isArray(records))throw new Error('Riwayat belum tersedia.');historyView={valid,records:records.filter(l=>l.user_id===state.user.id)};filterHistory();}
    catch(error){if(valid())document.getElementById('my-history-list').innerHTML=empty('Riwayat belum dapat dimuat',error.message,'<button class="btn btn-ghost" onclick="UserPortal.renderHistory()">Coba lagi</button>');}
  }
  function filterHistory(){
    if(!historyView?.valid())return;
    const method=document.getElementById('my-history-method').value,result=document.getElementById('my-history-result').value;
    const rows=historyView.records.filter(l=>(!method||l.method===method)&&(!result||l.result===result));
    document.getElementById('my-history-total').textContent=String(rows.length);document.getElementById('my-history-success').textContent=String(rows.filter(l=>l.result==='success').length);document.getElementById('my-history-failed').textContent=String(rows.filter(l=>['denied','failed','timeout'].includes(l.result)).length);
    document.getElementById('my-history-list').innerHTML=rows.length?timeline(rows):empty(historyView.records.length?'Tidak ada hasil untuk filter ini':'Belum ada riwayat akses',historyView.records.length?'Ubah pilihan metode atau hasil untuk melihat aktivitas lainnya.':'Aktivitas akan muncul setelah Anda menggunakan perangkat.');document.getElementById('my-history-caption').textContent=`Menampilkan ${rows.length} dari ${historyView.records.length} catatan terbaru perangkat ini.`;
  }
  function renderProfile(){
    const d=mySelectedDevice();
    setContent(`<div id="user-profile" class="user-portal">${header('Profil Saya','Identitas akun dan kesiapan akses smartlock Anda.')}<div class="user-profile-layout"><section class="panel user-profile-card"><div class="user-profile-avatar">${e(state.user.name.slice(0,1).toUpperCase())}</div><span class="user-state-pill ready">Akun pengguna</span><h3>${e(state.user.name)}</h3><p>${e(state.user.email)}</p><div class="info-row"><span>Status akun</span><strong>${state.user.is_active===false?'Tidak aktif':'Aktif'}</strong></div><div class="info-row"><span>Perangkat disetujui</span><strong>${state.devices.length}</strong></div><div class="info-row"><span>Terdaftar sejak</span><span>${state.user.created_at?e(fmtTime(state.user.created_at)):'—'}</span></div><button type="button" class="btn btn-danger-ghost" onclick="doLogout()">Keluar dari akun</button></section><div><section class="panel user-profile-rights"><div class="user-section-heading"><div><div class="eyebrow">RUANG AKSES ANDA</div><h3>Pengguna smartlock</h3></div><span class="user-registration-symbol face">${icon('shield')}</span></div><p>Anda dapat menggunakan perangkat dan metode yang disetujui owner, serta mendaftarkan wajah dan kartu milik sendiri.</p><ul class="user-rights-list"><li>${icon('check')} Memilih perangkat yang disetujui</li><li>${icon('check')} Menggunakan metode akses yang diizinkan</li><li>${icon('check')} Melihat riwayat akses sendiri</li><li class="muted">${icon('lock')} Pengaturan perangkat, radius, dan izin pengguna dikelola owner</li></ul><button class="btn btn-ghost" onclick="goTo('devices')">Lihat perangkat saya ${icon('arrow')}</button></section>${d?`<div class="overview-section-title"><div><h3>Identitas akses saya</h3><p>Untuk ${e(d.name)} · ${e(d.owner_name||'Owner perangkat')}</p></div></div>${registrations(d)}`:`<div class="panel">${empty('Belum ada akses perangkat','Identitas akses dapat disiapkan setelah owner menyetujui perangkat Anda.')}</div>`}</div></div></div>`);
    if(d)hydrate('user-profile',d);
  }
  document.addEventListener('smartlock:face-registered',event=>{
    if(state.user?.role!=='user'||event.detail?.userId!==state.user.id)return;
    faceStatusRevision++;
    const root=document.getElementById('user-home')||document.getElementById('user-profile');const d=mySelectedDevice();if(root&&d)faceStatus(root,true,d.can_use_face===true);
  });
  window.UserPortal={renderHome,renderDevices,renderNfc,registerNfc,renderHistory,filterHistory,renderProfile,refreshDevices,reset(){historyView=null;faceStatusRevision++;}};
})();
