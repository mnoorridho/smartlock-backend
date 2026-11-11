// UI-only checks: preferences, form preservation, and return navigation for both roles.
const assert = require('node:assert/strict');
const { chromium } = require('playwright');
const fs = require('node:fs'), path = require('node:path'), http = require('node:http');
const folder = path.join(__dirname, '../app/static_pages');
const assets = new Set(['dashboard.html','user-portal.js','user-portal.css','face-unlock.js','face-unlock-core.js','face-unlock.css']);
const server = http.createServer((req,res) => {
  const url = new URL(req.url,'http://local');
  if(url.pathname === '/auth/google/config'){res.setHeader('Content-Type','application/json');return res.end('{"enabled":false}');}
  const file = url.pathname === '/dashboard' ? 'dashboard.html' : path.basename(url.pathname);
  if(!assets.has(file)){res.writeHead(404);return res.end();}
  res.setHeader('Content-Type',file.endsWith('.html')?'text/html':file.endsWith('.css')?'text/css':'application/javascript');
  res.end(fs.readFileSync(path.join(folder,file)));
});
(async () => {
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  const origin = `http://127.0.0.1:${server.address().port}`;
  const browser = await chromium.launch({headless:true,channel:process.env.PLAYWRIGHT_CHANNEL || 'msedge'});
  try {
    const page = await browser.newPage({viewport:{width:390,height:844}}), errors=[];
    page.on('pageerror',e=>errors.push(e.message));
    await page.route('**/*',route=>{
      const url=new URL(route.request().url());
      if(url.origin!==origin)return route.abort();
      if(url.pathname==='/dashboard'||url.pathname.startsWith('/dashboard-assets/'))return route.continue();
      if(url.pathname==='/devices/')return route.fulfill({json:[{id:'test-device',name:'Test device',device_code:'TEST',can_use_face:true,can_use_nfc:true,can_use_quick:false,lock_status:'locked',door_state:'closed',owner_name:'Test owner',access_window_enabled:false}]});
      if(url.pathname==='/auth/google/config')return route.fulfill({json:{enabled:false}});
      if(url.pathname==='/auth/me/face-profile/status')return route.fulfill({json:{registered:false}});
      return route.fulfill({json:[]});
    });
    async function session(role){
      await page.goto(origin+'/dashboard');
      await page.evaluate(role=>{state.user={id:'test-user',name:'Test account',email:'test@example.com',role,is_active:true};state.token='test-only';state.apiBase=location.origin;enterShell();},role);
      await page.waitForFunction(()=>state.devices.length>0);
    }
    await page.goto(origin+'/dashboard');
    const login = page.locator('.login-appearance');
    await login.getByRole('button',{name:'Tema gelap',exact:true}).click();
    assert.equal(await page.locator('body').evaluate(el=>el.classList.contains('theme-light')),false);
    await page.reload();
    assert.equal(await login.getByRole('button',{name:'Tema gelap',exact:true}).getAttribute('aria-pressed'),'true');
    await login.getByRole('button',{name:'Tema terang',exact:true}).click();
    const input = page.locator('#login-screen input:visible').first();await input.fill('Form tetap tersimpan');
    await login.getByRole('button',{name:'Tema gelap',exact:true}).click();
    assert.equal(await input.inputValue(),'Form tetap tersimpan');
    await login.getByRole('button',{name:'Tema terang',exact:true}).click();
    const colors = await input.evaluate(el=>({text:getComputedStyle(el).color,bg:getComputedStyle(el).backgroundColor}));
    assert.equal(colors.bg,'rgb(255, 255, 255)');assert.equal(colors.text,'rgb(18, 21, 27)');
    for(const role of ['user','owner']) {
      await session(role);
      await page.waitForFunction(()=>state.user);
      const pages = role === 'user' ? ['devices','nfc','logs','settings'] : ['devices','logs','permissions','nfc','guest','settings'];
      for(const section of pages) {
        await page.evaluate(p=>goTo(p),section);
        const back = page.getByRole('button',{name:'Kembali ke Beranda',exact:true});
        await back.waitFor({state:'visible'});
        for(const theme of ['dark','light']) {
          await page.locator('.topbar-actions').getByRole('button',{name:theme==='dark'?'Tema gelap':'Tema terang',exact:true}).click();
          assert.equal(await page.evaluate(()=>state.currentPage),section);
          assert.equal(await page.locator('body').evaluate(el=>el.classList.contains('theme-light')),theme==='light');
        }
        assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),`${role} ${section} overflow`);
        const box=await back.boundingBox();assert.ok(box.height>=44);
        await back.click();assert.equal(await page.evaluate(()=>state.currentPage),'overview');
        assert.equal(await back.isVisible(),false);
      }
      await page.evaluate(()=>FaceUnlock.register());
      await page.locator('#face-screen').waitFor({state:'visible'});
      await page.locator('#face-screen').getByRole('button',{name:'Tema gelap',exact:true}).click();
      assert.equal(await page.locator('#face-screen').evaluate(el=>getComputedStyle(el).backgroundColor),'rgb(16, 20, 28)');
      await page.locator('#face-screen').getByRole('button',{name:'Kembali ke Beranda',exact:true}).click();
      assert.equal(await page.evaluate(()=>state.currentPage),'overview');
      assert.equal(await page.locator('#face-screen').isVisible(),false);
    }
    await session('user');
    await page.waitForFunction(()=>state.user?.role==='user');
    await page.setViewportSize({width:320,height:740});
    await page.evaluate(()=>goTo('settings'));
    assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'320px overflow');
    await page.screenshot({path:path.join(__dirname,'../docs/mobile/user-theme-back-mobile.png'),fullPage:true});
    assert.deepEqual(errors,[]);
    console.log('PASS: light/dark login persistence, readable inputs, both roles/all mobile menus, face return and 320px layout.');
  } finally { await browser.close();server.close(); }
})().catch(error=>{console.error(error);server.close();process.exitCode=1;});
