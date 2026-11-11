// Integration tests use a synthetic camera and deterministic model outputs, never a real face/lock.
const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const { chromium, devices } = require('playwright');
const assets = path.join(__dirname, '../app/static_pages');
const output = path.join(__dirname, '../docs/mobile');
const descriptor = [1, ...Array(127).fill(0)];
const profile = { model_version: 'face-api-1.7.15', descriptors: [descriptor,descriptor,descriptor], user_id:'test-user', user_name:'Akun Wajah Terdaftar' };
const fixture = { id: 'test-lock', name: 'Pintu Laboratorium', device_code: 'TEST', status: 'online', last_seen: new Date().toISOString(), lock_status: 'locked', door_state: 'closed', face_verification_enabled: true, owner_name:'Owner Laboratorium',can_use_face:true,can_use_nfc:true,can_use_quick:false };
const server = http.createServer((req, res) => {
  const route = new URL(req.url, 'http://localhost').pathname;
  const file = route === '/dashboard' ? 'dashboard.html' : route.startsWith('/dashboard-assets/') ? path.basename(route) : null;
  if (!file || !['dashboard.html','face-unlock.js','face-unlock-core.js','face-unlock.css','user-portal.js','user-portal.css'].includes(file)) { res.writeHead(404);res.end();return; }
  res.setHeader('Content-Type', file.endsWith('.html') ? 'text/html' : file.endsWith('.css') ? 'text/css' : 'application/javascript');
  res.end(fs.readFileSync(path.join(assets,file)));
});
(async () => {
  await new Promise(resolve => server.listen(0,'127.0.0.1',resolve));
  const origin = `http://127.0.0.1:${server.address().port}`;
  const browser = await chromium.launch({ headless: true, ...(process.env.PLAYWRIGHT_CHANNEL ? { channel: process.env.PLAYWRIGHT_CHANNEL } : {}) });
  const context = await browser.newContext({ ...devices['iPhone 13'] });
  const page = await context.newPage();
  const errors = [], posts = [], enrollments = [];
  let apiError = 0, missingProfile = false, pollCount = 0, holdFreshProfile = false, profileReads = 0, releaseProfile = null, outsideRadius=false, simulated=false;
  const myCards=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/*', async route => {
    const request = route.request(), url = new URL(request.url());
    if (url.origin !== origin) return route.abort();
    if (url.pathname === '/dashboard' || url.pathname.startsWith('/dashboard-assets/')) return route.continue();
    if (url.pathname === '/auth/google/config') return route.fulfill({json:{enabled:false}});
    if (url.pathname === '/auth/me/face-profile/status') return route.fulfill({json:{registered:enrollments.length>0}});
    if (url.pathname.endsWith('/face-precheck')) return route.fulfill(outsideRadius ? {status:403,json:{detail:'Anda di luar radius yang diizinkan owner.'}} : {json:{allowed:true,geofence_enabled:true}});
    if (url.pathname === '/auth/me/face-profile') {
      if(request.method()==='PUT'){enrollments.push(request.postDataJSON());return route.fulfill({json:{status:'registered'}});}
      profileReads++;
      if (holdFreshProfile && profileReads === 2) await new Promise(resolve => { releaseProfile = resolve; });
      try { return await route.fulfill(missingProfile ? {status:404,json:{detail:'Wajah belum terdaftar. Minta owner mendaftarkan wajah Anda.'}} : {json:profile}); } catch (_) { return; }
    }
    if (url.pathname === '/devices/') return route.fulfill({json:[fixture]});
    if (url.pathname === '/auth/users') return route.fulfill({json:[{ id:'test-user',name:'Test Owner',email:'test@example.com',role:'owner',is_active:true }]});
    if (url.pathname === '/auth/users/test-user/face-profile' && request.method() === 'PUT') { enrollments.push(request.postDataJSON()); return route.fulfill({json:{status:'registered'}}); }
    if(url.pathname==='/nfc-cards/'){
      if(request.method()==='POST'){const body=request.postDataJSON();assert.equal(body.user_email,undefined);myCards.push({...body,id:'my-card',user_id:'test-user',is_active:true});return route.fulfill({status:201,json:myCards.at(-1)});}
      return route.fulfill({json:myCards});
    }
    if (url.pathname.endsWith('/unlock')) {
      posts.push({body:request.postDataJSON(), authorization:request.headers().authorization,path:url.pathname});
      return route.fulfill(apiError ? {status:apiError,json:{detail:`Alasan khusus backend ${apiError}`}} : {json:{status:'command_sent',transaction_id:'test-tx'}});
    }
    if (url.pathname.endsWith('/commands/test-tx')) { pollCount++; return route.fulfill({json:{result:pollCount>1?'success':'pending',simulated}}); }
    if (url.pathname === '/devices/test-lock') return route.fulfill({json:{...fixture,door_state:'open'}});
    return route.fulfill({json:[]});
  });
  await page.addInitScript(() => {
    window.faceScenario = 'valid'; window.cameraCalls = 0; window.faceDetections = 0; window.gpsCalls = 0; window.testStreams = []; window.gpsDenied = false; window.gpsHold = false;
    Object.defineProperty(navigator,'geolocation',{value:{getCurrentPosition(ok,fail){
      window.gpsCalls++;
      if (window.gpsDenied) fail({code:1});
      else if(window.gpsHold)window.releaseTestGps=()=>ok({coords:{latitude:-7.05,longitude:110.4,accuracy:9},timestamp:Date.now()});
      else ok({coords:{latitude:-7.05,longitude:110.4,accuracy:9},timestamp:Date.now()});
    }}});
    Object.defineProperty(navigator.mediaDevices,'getUserMedia',{value: async () => {
      window.cameraCalls++;
      const canvas=document.createElement('canvas');canvas.width=640;canvas.height=854;
      const ctx=canvas.getContext('2d'); const pixels=ctx.createImageData(640,854);
      let seed=7;
      for(let i=0;i<pixels.data.length;i+=4){seed=(seed*16807)%2147483647;const c=65+(seed%130);pixels.data[i]=pixels.data[i+1]=pixels.data[i+2]=c;pixels.data[i+3]=255;}
      const paint=()=>{ctx.putImageData(pixels,0,0);ctx.fillStyle='#777';ctx.fillRect(0,0,8,8);};paint();
      const timer=setInterval(paint,60), stream=canvas.captureStream(20);
      window.testStreams.push(stream);stream.getTracks()[0].addEventListener('ended',()=>clearInterval(timer));
      return stream;
    }});
    const makeResult = canvas => {
      const oval=document.querySelector('.face-oval'), scale=Math.max(oval.clientWidth/canvas.width,oval.clientHeight/canvas.height), ox=(canvas.width*scale-oval.clientWidth)/2,oy=(canvas.height*scale-oval.clientHeight)/2;
      const b={x:(.18*oval.clientWidth+ox)/scale,y:(.15*oval.clientHeight+oy)/scale,width:.64*oval.clientWidth/scale,height:.7*oval.clientHeight/scale};
      if(window.faceScenario==='jitter')b.x+=(Math.floor(performance.now()/90)%2?.06:-.04)*oval.clientWidth/scale;
      if(window.faceScenario==='position')b.x=-b.width*.5;
      const points=Array.from({length:68},()=>({x:b.x+b.width*.5,y:b.y+b.height*.5}));
      const eye=(start,cx)=>{const w=b.width*.16,cy=b.y+b.height*.38;const shape=[[-.5,0],[-.25,-.125],[.25,-.125],[.5,0],[.25,.125],[-.25,.125]];shape.forEach(([x,y],i)=>points[start+i]={x:cx+x*w,y:cy+y*w});};
      eye(36,b.x+b.width*.3);eye(42,b.x+b.width*.7);
      points[30]={x:b.x+b.width*.5,y:b.y+b.height*.6};
      for(let i=48;i<60;i++)points[i]={x:b.x+b.width*.5+Math.cos(i*Math.PI/6)*b.width*.15,y:b.y+b.height*.78+Math.sin(i*Math.PI/6)*b.height*.025};
      if(window.faceScenario==='outer-landmark')points[0].x=-10;
      return {detection:{box:b,score:window.faceScenario==='moderate-confidence'?.65:.99},landmarks:{positions:points},descriptor:window.faceScenario==='mismatch'?new Float32Array([0,1,...Array(126).fill(0)]):new Float32Array([1,...Array(127).fill(0)])};
    };
    window.faceapi={tf:{ready:async()=>{}},nets:{tinyFaceDetector:{loadFromUri:async()=>{}},faceLandmark68Net:{loadFromUri:async()=>{}},faceRecognitionNet:{loadFromUri:async()=>{}}},TinyFaceDetectorOptions:class{},detectAllFaces(canvas){
      window.faceDetections++;
      const result=()=>window.faceScenario==='none'?[]:window.faceScenario==='multiple'?[makeResult(canvas),makeResult(canvas)]:[makeResult(canvas)];
      const task={withFaceLandmarks(){return task;},withFaceDescriptors(){return Promise.resolve(result());},then(resolve,reject){return Promise.resolve(result()).then(resolve,reject);}};return task;
    }};
  });
  try {
    await page.goto(origin+'/dashboard?demo=1&role=user');
    assert.equal(await page.locator('#demo-login-btn').count(),0);
    assert.equal(await page.evaluate(()=>typeof startDemo),'undefined');
    assert.equal(await page.locator('#shell').evaluate(el=>el.classList.contains('active')),false);
    await page.evaluate(()=>{state.user={id:'test-user',name:'Test Owner',role:'owner',email:'test@example.com',is_active:true};state.token='test-token';state.apiBase=location.origin;enterShell();});
    await page.waitForSelector('.access-action');
    async function status(pattern){await page.waitForFunction(pattern=>new RegExp(pattern).test(document.getElementById('face-status').textContent),pattern);}
    async function close(){await page.evaluate(()=>FaceUnlock.close());}
    async function openPhoto(scenario='valid'){
      await page.evaluate(s=>{window.faceScenario=s;FaceUnlock.open('test-lock');},scenario);
      await page.locator('#face-take-photo').waitFor({state:'visible'});
    }
    async function stopped(){assert.ok(await page.evaluate(()=>window.testStreams.every(s=>s.getTracks().every(t=>t.readyState==='ended'))));}
    let count=0;
    for(const [scenario,message] of [['none','Wajah belum terlihat'],['multiple','lebih dari satu'],['position','Mata|dalam foto|100']]){
      await openPhoto(scenario);
      const calls=await page.evaluate(()=>window.faceDetections);
      await page.waitForTimeout(250);
      assert.equal(await page.evaluate(()=>window.faceDetections),calls,'No automatic recognition before shutter');
      await page.locator('#face-take-photo').click();await status(message);
      assert.equal(posts.length,0);assert.equal(await page.locator('#face-retake').isVisible(),true);await stopped();await close();
    }
    await openPhoto('valid');
    assert.match(await page.locator('#face-hint').textContent(),/tempat yang terang/);
    const before=await page.evaluate(()=>window.faceDetections);
    await page.locator('#face-take-photo').click();await status('Perangkat mengonfirmasi');
    assert.equal(await page.evaluate(()=>window.faceDetections),before+1,'Unlock inspects exactly one snapshot');
    assert.equal(posts.length,++count);assert.equal(posts[0].body.face_verified,true);assert.equal(posts[0].body.accuracy_m,9);
    assert.match(await page.locator('#face-hint').textContent(),/Akun Wajah Terdaftar/);await stopped();await close();
    for(const scenario of ['moderate-confidence','outer-landmark']){await openPhoto(scenario);await page.locator('#face-take-photo').click();await status('Perangkat mengonfirmasi');assert.equal(posts.length,++count);await close();}
    simulated=true;await openPhoto();await page.locator('#face-take-photo').click();await status('Smartlock berhasil dibuka');
    assert.match(await page.locator('#face-status').textContent(),/Simulasi/);assert.equal(posts.length,++count);await close();simulated=false;
    await openPhoto('mismatch');await page.locator('#face-take-photo').click();await status('Pencocokan wajah ditolak');assert.match(await page.locator('#face-status').textContent(),/jarak.*batas owner/);assert.equal(posts.length,count);await stopped();await close();
    outsideRadius=true;const cameras=await page.evaluate(()=>window.cameraCalls);
    await page.evaluate(()=>FaceUnlock.open('test-lock'));await status('di luar radius');assert.equal(await page.evaluate(()=>window.cameraCalls),cameras);await close();outsideRadius=false;
    missingProfile=true;await page.evaluate(()=>FaceUnlock.open('test-lock'));await status('belum terdaftar');await close();missingProfile=false;
    await page.evaluate(()=>window.gpsDenied=true);await page.evaluate(()=>FaceUnlock.open('test-lock'));await status('Izin lokasi ditolak');await close();await page.evaluate(()=>window.gpsDenied=false);
    for(const code of [400,403,503]){apiError=code;await openPhoto();await page.locator('#face-take-photo').click();await status('Alasan khusus backend '+code);count++;await close();}apiError=0;
    holdFreshProfile=true;profileReads=0;await openPhoto();await page.locator('#face-take-photo').click();
    await page.waitForFunction(()=>document.getElementById('face-status').textContent.includes('Foto cocok'));
    while(!releaseProfile)await new Promise(r=>setTimeout(r,20));
    await close();releaseProfile();await page.waitForTimeout(200);assert.equal(posts.length,count,'Close cancels photo verification before unlock');holdFreshProfile=false;
    await openPhoto();await page.setViewportSize({width:844,height:390});await page.setViewportSize({width:390,height:844});await status('Verifikasi dijeda');await stopped();await close();
    await page.evaluate(()=>{window.faceScenario='valid';FaceUnlock.register();});await page.locator('#face-consent').click();
    await page.locator('#face-take-photo').waitFor({state:'visible'});
    const enrollmentCalls=await page.evaluate(()=>window.faceDetections);await page.waitForTimeout(250);
    assert.equal(await page.evaluate(()=>window.faceDetections),enrollmentCalls);
    await page.locator('#face-take-photo').click();await status('Gunakan foto wajah ini?');
    assert.equal(enrollments.length,0);await stopped();
    await page.locator('#face-retake').click();await page.locator('#face-take-photo').waitFor({state:'visible'});
    await page.locator('#face-take-photo').click();await status('Gunakan foto wajah ini?');
    await page.screenshot({path:path.join(output,'face-selfie-preview.png')});
    await page.locator('#face-save-photo').click();await status('berhasil didaftarkan');
    assert.equal(enrollments.length,1);assert.equal(enrollments[0].descriptors.length,1);assert.equal(posts.length,count);await close();
    await page.evaluate(()=>{state.user.role='user';state.user.name='Test User';enterShell();});await page.waitForSelector('.user-register-face');
    await page.locator('.user-register-face').click();await page.locator('#face-consent').click();await page.locator('#face-take-photo').click();await status('Gunakan foto wajah ini?');
    await page.locator('#face-save-photo').click();await status('berhasil didaftarkan');assert.equal(enrollments.length,2);await close();
    assert.deepEqual(errors,[]);
    console.log('PASS: no demo entry/data, manual single-photo enrollment and unlock, quality/identity/GPS denials, errors, cancellation, simulation ACK and verified name.');
  } finally {await browser.close();server.close();}
})().catch(error=>{console.error(error);server.close();process.exitCode=1;});
