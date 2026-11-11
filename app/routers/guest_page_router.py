from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["Guest Page (Web)"])

_TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "static_pages" / "guest_page.html"
_TEMPLATE = _TEMPLATE_PATH.read_text(encoding="utf-8")


@router.get("/guest/{token}", response_class=HTMLResponse, include_in_schema=False)
def guest_page(token: str):
    """
    Halaman publik yang dibuka tamu setelah scan QR. QR code seharusnya
    di-generate (oleh aplikasi/website) berisi URL ke sini, contoh:
      https://{base_url}/guest/{token}

    Halaman ini murni HTML+CSS+JS statis; semua logic validasi (PIN, waktu,
    batas pemakaian) tetap di backend lewat endpoint:
      GET  /guest-access/{token}          (preview info, dipanggil otomatis saat halaman dibuka)
      POST /guest-access/{token}/redeem   (submit PIN)

    include_in_schema=False supaya endpoint ini gak nyampah di Swagger UI
    (ini halaman web, bukan bagian dari API contract).
    """
    html = _TEMPLATE.replace("__TOKEN__", token)
    return HTMLResponse(content=html)
