// Run with Node.js and Playwright (npm install --no-save playwright).
// Uses mocked API responses; never connects to a lock or production database.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const { chromium, devices } = require('playwright');
const html = fs.readFileSync(path.join(__dirname, '../app/static_pages/dashboard.html'), 'utf8');
const output = path.join(__dirname, '../docs/mobile');
fs.mkdirSync(output, { recursive: true });
const server = http.createServer((req, res) => {
  const asset = new URL(req.url, 'http://localhost').pathname.match(/^\/dashboard-assets\/(face-unlock(?:-core)?\.js|face-unlock\.css|user-portal\.(?:js|css))$/);
  if (asset) {
    res.setHeader('Content-Type', asset[1].endsWith('.css') ? 'text/css' : 'application/javascript');
    res.end(fs.readFileSync(path.join(__dirname, '../app/static_pages', asset[1])));
    return;
  }
  res.setHeader('Content-Type', 'text/html; charset=utf-8');
  res.end(html);
});
const fixtures = Array.from({ length: 4 }, (_, i) => ({
  id: `device-${i}`, name: `Pintu Laboratorium ${i + 1}`, device_code: `LOCK-LAB-0${i + 1}`,
  status: 'online', lock_status: 'locked', door_state: 'closed',
  last_seen: new Date().toISOString(), location: 'Gedung Teknik',
  access_start_time: '07:00', access_end_time: '17:00', nfc_verification_enabled: true,
}));
async function noOverflow(page, label) {
  const sizes = await page.evaluate(() => ({ view: innerWidth, page: document.documentElement.scrollWidth }));
  assert.ok(sizes.page <= sizes.view + 1, `${label}: horizontal overflow ${JSON.stringify(sizes)}`);
}
(async () => {
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const origin = `http://127.0.0.1:${server.address().port}`;
  const browser = await chromium.launch({ headless: true, ...(process.env.PLAYWRIGHT_CHANNEL ? { channel: process.env.PLAYWRIGHT_CHANNEL } : {}) });
  const errors = [];
  try {
    async function open(options) {
      const context = await browser.newContext(options);
      // Date picker dependency is outside these isolated layout checks.
      await context.addInitScript(() => {
        window.flatpickr = () => [];
        window.L = { divIcon: () => ({}) };
        window.QRCode = function (element, options) {
          const marker = document.createElement('span');
          marker.dataset.qrTarget = options.text;
          marker.textContent = 'QR TEST';
          element.append(marker);
        };
        window.QRCode.CorrectLevel = { M: 1 };
      });
      const page = await context.newPage();
      page.on('pageerror', error => errors.push(error.message));
      await page.route('**/*', route => {
        const url = new URL(route.request().url());
        if (url.origin !== origin) return route.abort();
        if (url.pathname === '/dashboard' || url.pathname.startsWith('/dashboard-assets/')) return route.continue();
        let body = [];
        if (url.pathname === '/devices/') body = fixtures;
        if (url.pathname === '/auth/google/config') body = { enabled: false };
        return route.fulfill({ json: body });
      });
      await page.goto(origin + '/dashboard');
      const qrCardDisplay = await page.locator('.webapp-qr-card').evaluate(el => getComputedStyle(el).display);
      if (options.viewport?.width >= 900 || (!options.viewport && options.screen?.width >= 900)) {
        assert.notEqual(qrCardDisplay, 'none', 'desktop login should show the Web App QR card');
      } else {
        assert.equal(qrCardDisplay, 'none', 'mobile login should hide the desktop QR card');
      }
      assert.equal(await page.locator('#webapp-qr-url').textContent(), origin + '/dashboard');
      await page.evaluate(() => {
        // Map tiles/Leaflet are unrelated to shell layout and blocked with other CDNs.
        initGeofenceMap = () => {};
        state.user = { id: 'owner', name: 'Pemilik', email: 'owner@example.test', role: 'owner', is_active: true };
        state.token = 'test-only';
        state.apiBase = location.origin;
        enterShell();
      });
      await page.waitForSelector('.overview-device-card');
      return { context, page };
    }
    const { context, page } = await open({ ...devices['iPhone 13'] });
    assert.equal(await page.locator('#mobile-nav').isVisible(), true);
    assert.equal(await page.locator('#sidebar').evaluate(el => el.inert), true);
    await noOverflow(page, 'mobile overview');
    const carousel = page.locator('.overview-device-grid');
    assert.ok(await carousel.evaluate(el => el.scrollWidth > el.clientWidth));
    await carousel.evaluate(el => { el.scrollLeft = el.clientWidth; });
    await page.waitForFunction(() => document.querySelector('.overview-device-grid').scrollLeft > 0);
    await carousel.evaluate(el => { el.scrollLeft = 0; });
    for (const button of await page.locator('#mobile-nav button').all()) {
      const box = await button.boundingBox();
      assert.ok(box.width >= 44 && box.height >= 44);
    }
    await page.screenshot({ path: path.join(output, 'mobile-preview.png'), fullPage: true });
    await page.locator('#mobile-more').click();
    assert.equal(await page.locator('#sidebar').getAttribute('aria-modal'), 'true');
    await page.locator('#sidebar [data-page="settings"]').click();
    assert.equal(await page.locator('#page-title').textContent(), 'Pengaturan');
    assert.equal(await page.locator('#drawer-toggle').getAttribute('aria-expanded'), 'false');
    await page.locator('#mobile-nav [data-page="devices"]').click();
    await noOverflow(page, 'mobile devices');
    assert.equal(await page.locator('.device-picker button').count(), 4);
    await page.locator('#mobile-nav [data-page="logs"]').click();
    await page.waitForSelector('.empty-state');
    await noOverflow(page, 'mobile logs');
    for (const [name, selector] of [['permissions', '#perm-list .empty-state'], ['nfc', '#nfc-list .empty-state'], ['guest', '#guest-list .empty-state']]) {
      await page.evaluate(name => goTo(name), name);
      await page.waitForSelector(selector);
      await noOverflow(page, 'mobile ' + name);
    }
    // Exercise asynchronous data tables without requiring third-party chart/map CDNs.
    await page.evaluate(() => setContent('<div id="async-table"></div>'));
    await page.evaluate(() => document.getElementById('async-table').innerHTML = '<table><tr><td>Data</td></tr></table>');
    await page.waitForSelector('.mobile-table-scroll');
    await noOverflow(page, 'async table');
    await page.setViewportSize({ width: 844, height: 390 });
    await page.waitForSelector('#portrait-overlay', { state: 'visible' });
    assert.equal(await page.locator('#app-root').isVisible(), false);
    assert.equal(await page.locator('#app-root').evaluate(el => el.inert), true);
    assert.equal(new URL(page.url()).pathname, '/dashboard');
    await page.screenshot({ path: path.join(output, 'mobile-landscape-preview.png') });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.waitForSelector('#portrait-overlay', { state: 'hidden' });
    await page.evaluate(() => { state.user.role = 'user'; enterShell(); });
    await page.waitForSelector('.overview-device-card');
    await page.locator('#mobile-more').click();
    assert.equal(await page.locator('#sidebar .owner-only:visible').count(), 0);
    await page.keyboard.press('Escape');
    await page.evaluate(() => { applyTheme('dark'); goTo('overview'); });
    await noOverflow(page, 'dark theme');
    await page.setViewportSize({ width: 320, height: 568 });
    await page.waitForFunction(() => innerWidth === 320);
    await noOverflow(page, '320px overview');
    await page.evaluate(() => goTo('devices'));
    await noOverflow(page, '320px devices');
    await page.evaluate(() => { state.user.role = 'owner'; goTo('devices'); });
    await noOverflow(page, '320px owner devices');
    await page.evaluate(() => doLogout());
    assert.equal(await page.locator('#mobile-nav').isVisible(), false);
    await noOverflow(page, '320px login');
    await context.close();
    const desktop = await open({ viewport: { width: 1440, height: 1000 } });
    assert.equal(await desktop.page.locator('#mobile-nav').isVisible(), false);
    assert.equal(await desktop.page.locator('#sidebar').isVisible(), true);
    assert.equal(await desktop.page.locator('#sidebar').evaluate(el => el.inert), false);
    assert.equal(await desktop.page.locator('#webapp-qr-open').isVisible(), true);
    await desktop.page.locator('#webapp-qr-open').click();
    await desktop.page.waitForSelector('#webapp-qr-overlay:not([hidden])');
    assert.equal(await desktop.page.locator('#webapp-qr-dialog-url').textContent(), origin + '/dashboard');
    assert.equal(await desktop.page.locator('#webapp-qr-dialog-code [data-qr-target]').getAttribute('data-qr-target'), origin + '/dashboard');
    await desktop.page.keyboard.press('Escape');
    await desktop.page.waitForSelector('#webapp-qr-overlay[hidden]');
    await noOverflow(desktop.page, 'desktop overview');
    await desktop.page.screenshot({ path: path.join(output, 'desktop-preview.png'), fullPage: true });
    await desktop.page.setViewportSize({ width: 760, height: 900 });
    await desktop.page.waitForSelector('#mobile-nav', { state: 'visible' });
    await desktop.page.setViewportSize({ width: 900, height: 500 });
    await desktop.page.waitForFunction(() => !document.documentElement.classList.contains('is-mobile'));
    assert.equal(await desktop.page.locator('#portrait-overlay').isVisible(), false);
    assert.equal(await desktop.page.locator('#sidebar').evaluate(el => el.inert), false);
    await desktop.context.close();
    // A touch-enabled Windows laptop must retain the desktop layout in landscape.
    const laptop = await open({ viewport: { width: 1366, height: 768 }, screen: { width: 1366, height: 768 }, hasTouch: true });
    assert.equal(await laptop.page.locator('#mobile-nav').isVisible(), false);
    assert.equal(await laptop.page.locator('#portrait-overlay').isVisible(), false);
    assert.equal(await laptop.page.locator('#webapp-qr-open').isVisible(), true);
    await laptop.context.close();
    assert.deepEqual(errors, [], 'browser JavaScript errors');
    console.log('PASS: mobile/desktop layouts, navigation, roles, carousels, touch targets, tables, themes, portrait overlay and URL continuity.');
  } finally {
    await browser.close();
    server.close();
  }
})().catch(error => { console.error(error); server.close(); process.exitCode = 1; });
