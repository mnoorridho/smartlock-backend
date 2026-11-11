"""Preview UI with simulated data only; no database, account, or hardware access."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

DASHBOARD = Path(__file__).resolve().parents[1] / 'app' / 'static_pages' / 'dashboard.html'


class PreviewHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        route = urlsplit(self.path).path
        assets = {'face-unlock.css', 'face-unlock.js', 'face-unlock-core.js', 'user-portal.js', 'user-portal.css'}
        if route in ('/', '/dashboard'):
            body, content_type = DASHBOARD.read_bytes(), 'text/html; charset=utf-8'
        elif route.startswith('/dashboard-assets/') and route.rsplit('/', 1)[-1] in assets:
            asset = DASHBOARD.parent / route.rsplit('/', 1)[-1]
            body = asset.read_bytes()
            content_type = 'text/css' if asset.suffix == '.css' else 'application/javascript'
        elif route == '/auth/google/config':
            body, content_type = b'{"enabled":false,"client_id":null}', 'application/json'
        else:
            self.send_error(404, 'UI preview only; use the real backend for accounts.')
            return
        self.send_response(200)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    print(f'Pratinjau demo: http://127.0.0.1:{args.port}/dashboard?demo=1', flush=True)
    ThreadingHTTPServer(('127.0.0.1', args.port), PreviewHandler).serve_forever()
