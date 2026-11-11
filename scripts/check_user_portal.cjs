// Read-only UI scenarios; no camera, database or hardware is used.
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),http=require('node:http');
const {chromium,devices}=require('playwright');
const folder=path.join(__dirname,'../app/static_pages'),output=path.join(__dirname,'../docs/mobile');
const files=new Set(['dashboard.html','face-unlock.js','face-unlock-core.js','face-unlock.css','user-portal.js','user-portal.css']);
const server=http.createServer((req,res)=>{const pathname=new URL(req.url,'http://local').pathname;const name=pathname==='/dashboard'?'dashboard.html':pathname.startsWith('/dashboard-assets/')?path.basename(pathname):'';if(!files.has(name)){res.writeHead(404);res.end();return;}res.setHeader('Content-Type',name.endsWith('.html')?'text/html':name.endsWith('.css')?'text/css':'application/javascript');res.end(fs.readFileSync(path.join(folder,name)));});
(async()=>{
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  const origin=`http://127.0.0.1:${server.address().port}`;
  const browser=await chromium.launch({headless:true,...(process.env.PLAYWRIGHT_CHANNEL?{channel:process.env.PLAYWRIGHT_CHANNEL}:{})});
  const context=await browser.newContext({viewport:{width:1440,height:1000}}),page=await context.newPage();
  const errors=[],writes=[];page.on('pageerror',error=>errors.push(error.message));
  let cardError=false;
  const approved=[{id:'lab',name:'Pintu Laboratorium',device_code:'LOCK-LAB-01',owner_name:'Owner Laboratorium',location:'Gedung Teknik · Lantai 2',lock_status:'locked',door_state:'closed',last_seen:new Date().toISOString(),can_use_face:true,can_use_nfc:true,can_use_quick:false,latitude:-7.05,longitude:110.4,geofence_radius_m:100,access_start_time:'07:00',access_end_time:'17:00'}, {id:'library',name:'Pintu Perpustakaan',device_code:'LOCK-LIB-01',owner_name:'Owner Perpustakaan',location:'Gedung Perpustakaan',lock_status:'locked',door_state:'closed',last_seen:null,can_use_face:false,can_use_nfc:true,can_use_quick:false}];
  const records=[{id:'a',user_id:'member',method:'face',result:'success',timestamp:new Date().toISOString(),note:'Akses wajah akun saya berhasil'},{id:'b',user_id:'member',method:'nfc',result:'denied',timestamp:new Date(Date.now()-60000).toISOString(),note:'Kartu saya ditolak'},{id:'c',user_id:'member',method:'manual',result:'pending',timestamp:new Date(Date.now()-120000).toISOString(),note:'Menunggu perangkat'},{id:'foreign',user_id:'other',method:'face',result:'success',timestamp:new Date().toISOString(),note:'PRIVATE OTHER USER'}];
  const cards=[{id:'one',device_id:'lab',user_id:'member',label:'Kartu Utama',card_uid:'AA:01',is_active:true},{id:'two',device_id:'lab',user_id:'member',label:'Kartu Cadangan',card_uid:'AA:02',is_active:false}];
  await page.route('**/*',route=>{const request=route.request(),url=new URL(request.url());if(url.origin!==origin)return route.abort();if(url.pathname==='/dashboard'||url.pathname.startsWith('/dashboard-assets/'))return route.continue();if(request.method()!=='GET'){writes.push(url.pathname);return route.fulfill({status:403,json:{detail:'No writes in this test'}});}if(url.pathname==='/auth/google/config')return route.fulfill({json:{enabled:false}});if(url.pathname==='/devices/')return route.fulfill({json:approved});if(url.pathname==='/auth/me/face-profile/status')return route.fulfill({json:{registered:false,updated_at:null}});if(url.pathname==='/nfc-cards/')return route.fulfill(cardError?{status:503,json:{detail:'Koneksi kartu terputus'}}:{json:cards.filter(c=>c.device_id===url.searchParams.get('device_id'))});if(url.pathname.endsWith('/logs'))return route.fulfill({json:records});return route.fulfill({json:[]});});
  async function shot(name){await page.evaluate(()=>{document.activeElement?.blur();window.scrollTo(0,0);});await page.screenshot({path:path.join(output,name),fullPage:true});}
  async function noOverflow(label){const size=await page.evaluate(()=>({view:innerWidth,width:document.documentElement.scrollWidth}));assert.ok(size.width<=size.view+1,label+JSON.stringify(size));}
  try{
    await page.goto(origin+'/dashboard');
    await page.evaluate(()=>{state.user={id:'member',name:'Pengguna Smartlock',email:'member@example.com',role:'user',is_active:true,created_at:'2026-10-01T00:00:00Z'};state.token='test-only';state.apiBase=location.origin;enterShell();});
    await page.waitForFunction(()=>document.getElementById('user-active-cards')?.textContent==='1');
    assert.equal(await page.locator('#user-home .overview-metric').count(),4);
    assert.equal(await page.locator('.user-registration-card').count(),2);
    assert.equal(await page.locator('.user-method').nth(2).isDisabled(),true);
    assert.equal(await page.locator('.user-timeline-item').count(),3);
    assert.equal(await page.getByText('PRIVATE OTHER USER').count(),0);
    await noOverflow('desktop home');
    await shot('user-home-desktop.png');
    await page.setViewportSize({width:390,height:844});await page.waitForFunction(()=>document.documentElement.classList.contains('is-mobile'));
    await noOverflow('mobile home');await shot('user-home-mobile.png');
    await page.evaluate(()=>goTo('devices'));await page.waitForSelector('.user-device-choice');
    assert.equal(await page.locator('.user-device-choice').count(),2);
    await page.locator('.user-device-choice').nth(1).click();
    assert.equal(await page.locator('.user-method').first().isDisabled(),true);
    assert.match(await page.locator('.feature-top h3').textContent(),/Perpustakaan/);
    await noOverflow('mobile devices');await shot('user-devices-mobile.png');
    await page.locator('.user-device-choice').first().click();await page.evaluate(()=>goTo('nfc'));
    await page.waitForFunction(()=>document.getElementById('my-nfc-total')?.textContent==='2');
    assert.equal(await page.locator('.user-nfc-card').count(),2);assert.equal(await page.locator('.user-nfc-card.inactive button').isDisabled(),true);
    await page.locator('#my-nfc-register').click();assert.match(await page.locator('#my-nfc-feedback').textContent(),/nama/);assert.deepEqual(writes,[]);
    await noOverflow('mobile NFC');await shot('user-nfc-mobile.png');
    cardError=true;await page.evaluate(()=>UserPortal.renderNfc());await page.waitForFunction(()=>document.getElementById('my-nfc-list')?.textContent.includes('Koneksi kartu terputus'));cardError=false;
    await page.evaluate(()=>goTo('logs'));await page.waitForFunction(()=>document.getElementById('my-history-total')?.textContent==='3');
    assert.equal(await page.getByText('PRIVATE OTHER USER').count(),0);
    await page.locator('#my-history-method').selectOption('face');assert.equal(await page.locator('.user-timeline-item').count(),1);
    await page.locator('#my-history-result').selectOption('denied');assert.match(await page.locator('#my-history-list').textContent(),/Tidak ada hasil/);
    await page.locator('#my-history-method').selectOption('');assert.equal(await page.locator('.user-timeline-item').count(),1);
    await noOverflow('mobile history');await shot('user-history-mobile.png');
    await page.evaluate(()=>goTo('settings'));await page.waitForFunction(()=>document.querySelector('[data-face-status]')?.textContent==='Belum terdaftar');
    assert.equal(await page.locator('.theme-options').count(),0);assert.equal(await page.locator('#face-enroll-user').count(),0);
    await page.evaluate(()=>document.dispatchEvent(new CustomEvent('smartlock:face-registered',{detail:{userId:state.user.id}})));
    assert.equal(await page.locator('[data-face-status]').textContent(),'Terdaftar');
    await page.evaluate(()=>goTo('permissions'));assert.equal(await page.locator('#perm-user-select').count(),0);
    await noOverflow('mobile profile');await shot('user-profile-mobile.png');
    for(const name of ['overview','devices','nfc','logs','settings']){await page.setViewportSize({width:320,height:568});await page.evaluate(name=>goTo(name),name);await noOverflow('320px '+name);}
    await page.evaluate(()=>{applyTheme('dark');goTo('overview');});await noOverflow('dark home');
    await page.setViewportSize({width:1440,height:1000});await page.waitForFunction(()=>!document.documentElement.classList.contains('is-mobile'));await noOverflow('dark desktop');
    assert.deepEqual(writes,[]);assert.deepEqual(errors,[]);
    console.log('PASS: detailed user home/devices/NFC/history/profile, status truth, private activity, filters, validation, error states, role limits and responsive layouts.');
  }finally{await browser.close();server.close();}
})().catch(error=>{console.error(error);server.close();process.exitCode=1;});
