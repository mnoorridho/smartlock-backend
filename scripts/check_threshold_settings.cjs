// Real local-test API plus mobile UI. Only a temporary device's permission is changed.
const {chromium,devices}=require('playwright');
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const origin='http://127.0.0.1:8000';
const saved=JSON.parse(fs.readFileSync(path.join(__dirname,'../.local/phone-test-accounts.json'),'utf8'));
(async()=>{
  const browser=await chromium.launch({headless:true,channel:'msedge'});
  const context=await browser.newContext({...devices['iPhone 13'],deviceScaleFactor:1}),page=await context.newPage();
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  let deviceId,ownerToken;
  async function api(method,url,body,token){const response=await context.request.fetch(origin+url,{method,data:body,headers:token?{Authorization:'Bearer '+token}:{}});assert.ok(response.ok(),`${method} ${url}: ${response.status()}`);return response.status()===204?null:response.json();}
  try{
    assert.equal((await api('GET','/local-test/info')).simulator_enabled,true);
    const response=await context.request.post(origin+'/auth/login',{form:{username:saved.accounts.owner.email,password:saved.accounts.owner.password}});
    const login=await response.json();ownerToken=login.access_token;assert.ok(ownerToken);
    const device=await api('POST','/devices/',{device_code:'UI-CHECK-'+Date.now(),name:'Temporary threshold UI'},ownerToken);deviceId=device.id;
    const permission=await api('POST','/permissions/',{device_id:deviceId,user_email:saved.accounts.user.email},ownerToken);
    await page.route('**/*',route=>new URL(route.request().url()).origin===origin?route.continue():route.abort());
    await page.goto(origin+'/dashboard');
    await page.evaluate(({login,deviceId})=>{state.user=login.user;state.token=login.access_token;state.apiBase=location.origin;state.selectedDeviceId=deviceId;enterShell();},{login,deviceId});
    await page.waitForFunction(()=>state.devices.length>0);
    await page.evaluate(()=>goTo('settings'));
    await page.locator('#threshold-device').selectOption(deviceId);
    await page.waitForFunction(()=>document.getElementById('threshold-user')?.options.length===1);
    assert.equal(await page.locator('#face-match-threshold').inputValue(),'0.45');
    await page.locator('#face-match-threshold').fill('0.38');
    const change=page.waitForResponse(r=>r.url().endsWith('/permissions/'+permission.id)&&r.request().method()==='PATCH');
    await page.locator('#threshold-save').click();assert.equal((await change).status(),200);
    const list=await api('GET','/permissions/?device_id='+deviceId,null,ownerToken);assert.equal(list[0].face_match_threshold,.38);
    await page.evaluate(()=>goTo('overview'));await page.evaluate(()=>goTo('settings'));
    await page.locator('#threshold-device').selectOption(deviceId);
    await page.waitForFunction(()=>document.getElementById('face-match-threshold')?.value==='0.38');
    assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
    await page.locator('#face-threshold-panel').screenshot({path:path.join(__dirname,'../docs/mobile/owner-face-threshold.png')});
    await page.evaluate(()=>{state.user.role='user';goTo('settings');});
    assert.equal(await page.locator('#face-threshold-panel').count(),0);
    assert.deepEqual(errors,[]);
    console.log('PASS: owner mobile threshold save/persistence, scoped device/user, and user panel exclusion.');
  }finally{
    if(deviceId&&ownerToken)await api('DELETE','/devices/'+deviceId,null,ownerToken);
    await browser.close();
  }
})().catch(error=>{console.error(error);process.exitCode=1;});
