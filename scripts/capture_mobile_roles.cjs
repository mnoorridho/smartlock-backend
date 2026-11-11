// Capture current local-test accounts; read-only UI, no unlock commands.
const {chromium, devices}=require('playwright');
const path=require('node:path');
const fs=require('node:fs');
const accounts=JSON.parse(fs.readFileSync(path.join(__dirname,'../.local/phone-test-accounts.json'),'utf8')).accounts;
(async()=>{
  const browser=await chromium.launch({headless:true,channel:'msedge'});
  try{
    for(const role of ['owner','user']){
      const context=await browser.newContext({...devices['iPhone 13'],deviceScaleFactor:1});
      const page=await context.newPage();
      await page.route('**/*',route=>{
        const url=new URL(route.request().url());
        if(url.hostname==='127.0.0.1')return route.continue();
        return route.abort();
      });
      const response=await context.request.post('http://127.0.0.1:8000/auth/login',{form:{username:accounts[role].email,password:accounts[role].password}});
      const login=await response.json();
      if(!login.access_token)throw new Error('Local-test login failed');
      await page.goto('http://127.0.0.1:8000/dashboard',{waitUntil:'networkidle'});
      await page.evaluate(login=>{state.user=login.user;state.token=login.access_token;state.apiBase=location.origin;enterShell();},login);
      await page.waitForFunction(role=>state.user?.role===role,role);
      await page.evaluate(()=>{applyTheme('light');setMobileDrawer(false);});
      await page.screenshot({path:path.join(__dirname,`../docs/mobile/latest-${role}-mobile-home.png`),animations:'disabled'});
      await page.evaluate(()=>goTo('devices'));
      await page.getByRole('button',{name:'Kembali ke Beranda',exact:true}).waitFor({state:'visible'});
      await page.screenshot({path:path.join(__dirname,`../docs/mobile/latest-${role}-mobile-devices.png`),animations:'disabled'});
      console.log(`${role}: mobile home and devices captured at 390 × 664`);
      await context.close();
    }
  }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
