from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.routers import (
    auth_router,
    devices_router,
    hardware_router,
    permissions_router,
    guest_access_router,
    guest_page_router,
    nfc_router,
    dashboard_router,
)
from app.mqtt_client import mqtt_bridge

# Skema database sekarang dikelola lewat Alembic migration (folder alembic/),
# BUKAN lagi otomatis dibuat saat aplikasi start. Jalankan `alembic upgrade head`
# sebelum start server pertama kali, dan setiap kali ada migration baru.
# (Lihat README bagian "Migrasi database (Alembic)".)

app = FastAPI(
    title="Smartlock Project 1 - Backend API",
    description="Backend Smart Lock untuk autentikasi, validasi geofence, jam akses pintu, manajemen perangkat, guest access, dan audit log.",
    version="0.1.0",
)


@app.exception_handler(RequestValidationError)
async def registration_validation_error(request, error):
    if request.url.path == '/auth/register':
        # Do not return Pydantic's rejected input, which can contain the password.
        messages = [item['msg'].removeprefix('Value error, ') for item in error.errors()]
        return JSONResponse(status_code=422, content={'detail': ' '.join(messages)})
    return await request_validation_exception_handler(request, error)

# CORS: izinkan request dari origin manapun (termasuk file lokal seperti
# smartlock-dashboard.html yang dibuka langsung via file://, dan nanti web
# dashboard yang di-hosting terpisah dari backend). allow_origins=["*"] ini
# cukup buat tahap pengujian/capstone -- untuk produksi sebaiknya dibatasi
# ke domain frontend yang spesifik.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,  # harus False kalau allow_origins masih "*"
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router.router)
app.include_router(devices_router.router)
app.include_router(hardware_router.router)
app.include_router(permissions_router.router)
app.include_router(guest_access_router.router)
app.include_router(guest_page_router.router)
app.include_router(nfc_router.router)
app.include_router(dashboard_router.router)


@app.on_event("startup")
def on_startup():
    mqtt_bridge.start()


@app.on_event("shutdown")
def on_shutdown():
    mqtt_bridge.stop()


@app.get("/")
def root():
    return {"status": "ok", "message": "Smartlock backend jalan 🚀"}


@app.get("/health")
def health_check():
    return {"status": "healthy"}
