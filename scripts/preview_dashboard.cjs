// UI-only preview. No database, credentials, accounts, or hardware connections.
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const file = path.join(__dirname, '../app/static_pages/dashboard.html');
const port = Number(process.env.PORT || 8766);
http.createServer((req, res) => {
  const route = new URL(req.url, 'http://localhost').pathname;
  const asset = route.match(/^\/dashboard-assets\/(face-unlock(?:-core)?\.js|face-unlock\.css|user-portal\.(?:js|css))$/);
  if (req.method === 'GET' && asset) {
    res.writeHead(200, { 'Content-Type': asset[1].endsWith('.css') ? 'text/css' : 'application/javascript', 'Cache-Control': 'no-store' });
    res.end(fs.readFileSync(path.join(path.dirname(file), asset[1])));
    return;
  }
  if (req.method === 'GET' && (route === '/' || route === '/dashboard')) {
    res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store' });
    res.end(fs.readFileSync(file));
  } else if (req.method === 'GET' && route === '/auth/google/config') {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ enabled: false, client_id: null }));
  } else {
    res.writeHead(404, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ detail: 'Server ini hanya untuk pratinjau demo. Login akun asli memerlukan backend FastAPI.' }));
  }
}).listen(port, '127.0.0.1', () => console.log(`Demo: http://127.0.0.1:${port}/dashboard?demo=1`));
