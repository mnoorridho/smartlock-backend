from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from fastapi.responses import FileResponse
from fastapi import HTTPException

router = APIRouter(tags=["Dashboard (Web)"])

_TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "static_pages" / "dashboard.html"


@router.get("/dashboard-assets/{filename}", include_in_schema=False)
def dashboard_asset(filename: str):
    if filename not in {"face-unlock.css", "face-unlock.js", "face-unlock-core.js", "user-portal.js", "user-portal.css"}:
        raise HTTPException(status_code=404)
    return FileResponse(_TEMPLATE_PATH.parent / filename, headers={'Cache-Control': 'no-store'})


@router.get("/dashboard", response_class=HTMLResponse, include_in_schema=False)
def dashboard_page():
    """
    Sajikan web dashboard (smartlock-dashboard.html) LANGSUNG dari backend,
    bukan dibuka sebagai file lokal (file://) di browser.

    Alasan kenapa ini penting -- BUKAN cuma soal kepraktisan:
    Kalau dashboard dibuka dari file lokal sementara API-nya diakses lewat
    ngrok, browser menganggap keduanya origin yang BEDA TOTAL (file:// vs
    https://xxx.ngrok-free.dev), jadi kena aturan CORS. Ternyata ngrok (versi
    gratis) punya perilaku aneh: request GET yang butuh header Authorization
    (dipakai di HAMPIR SEMUA endpoint selain login) gagal di-terima browser
    walau di server balikan status 200 OK -- kemungkinan besar ngrok
    memodifikasi/duplikasi header CORS di response untuk request jenis itu.
    Request tanpa Authorization header (seperti login) tidak kena masalah ini.

    Solusinya: sajikan dashboard ini dari domain yang SAMA PERSIS dengan API
    (baik itu domain ngrok, atau nanti domain hosting beneran). Kalau
    dashboard & API satu origin, browser gak perlu proses CORS sama sekali
    untuk fetch API-nya -- otomatis nyelesain masalah di atas.

    File HTML-nya dibaca ulang setiap request (bukan di-cache saat startup)
    supaya kalau file dashboard.html diganti/diupdate, tinggal refresh
    browser tanpa perlu restart backend.
    """
    html = _TEMPLATE_PATH.read_text(encoding="utf-8")
    return HTMLResponse(content=html)
