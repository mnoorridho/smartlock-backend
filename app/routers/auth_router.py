from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import datetime
from fastapi import Response

from app.database import get_db
from app import models, schemas, auth
from app.config import settings
from app.face_diagnostics import FaceDiagnostic, record as record_face_diagnostic, latest as latest_face_diagnostics

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post('/me/face-diagnostics', status_code=204)
def save_face_diagnostic(payload: FaceDiagnostic, current_user: models.User = Depends(auth.get_current_user)):
    record_face_diagnostic(current_user.id, payload)


@router.get('/me/face-diagnostics')
def get_face_diagnostics(response: Response, current_user: models.User = Depends(auth.get_current_user)):
    response.headers['Cache-Control'] = 'no-store'
    return {'records': latest_face_diagnostics(current_user.id)}


@router.post("/register", response_model=schemas.UserOut, status_code=status.HTTP_201_CREATED)
def register(payload: schemas.UserRegister, db: Session = Depends(get_db)):
    existing = db.query(models.User).filter(models.User.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email sudah terdaftar")

    # Owner pertama yang daftar otomatis jadi role "owner"; selanjutnya role "user".
    is_first_user = db.query(models.User).count() == 0
    user = models.User(
        name=payload.name,
        email=payload.email,
        password_hash=auth.hash_password(payload.password),
        role=models.UserRole.owner if is_first_user else models.UserRole.user,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=schemas.Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    # OAuth2PasswordRequestForm pakai field "username", kita perlakukan sebagai email.
    user = db.query(models.User).filter(models.User.email == form_data.username).first()
    if not user or not auth.verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email atau password salah",
        )
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Akun tidak aktif")

    token = auth.create_access_token({"sub": user.id, "role": user.role.value})
    return {"access_token": token, "token_type": "bearer", "user": user}


class GoogleCredential(BaseModel):
    credential: str = Field(min_length=20, max_length=10000)


@router.get("/google/config")
def google_login_config():
    """Konfigurasi publik untuk menampilkan tombol Google Identity Services."""
    client_id = settings.google_client_id.strip()
    return {"enabled": bool(client_id), "client_id": client_id if client_id else None}


@router.post("/google", response_model=schemas.Token)
def login_with_google(payload: GoogleCredential, db: Session = Depends(get_db)):
    """Verifikasi ID token Google di server lalu login ke akun Smart Lock yang sudah ada.

    Endpoint ini sengaja tidak membuat akun/role baru otomatis agar login Google tidak
    dapat memberi hak owner. Pengguna harus mendaftar terlebih dahulu memakai email yang sama.
    """
    client_id = settings.google_client_id.strip()
    if not client_id:
        raise HTTPException(status_code=503, detail="Login Google belum dikonfigurasi. Isi GOOGLE_CLIENT_ID di file .env lalu restart backend.")

    try:
        from google.oauth2 import id_token
        from google.auth.transport import requests as google_requests
        claims = id_token.verify_oauth2_token(
            payload.credential, google_requests.Request(), audience=client_id
        )
    except ValueError:
        raise HTTPException(status_code=401, detail="Token Google tidak valid atau sudah kedaluwarsa.")
    except Exception:
        raise HTTPException(status_code=502, detail="Gagal memverifikasi akun ke Google. Coba lagi.")

    email = str(claims.get("email", "")).strip().lower()
    if not email or claims.get("email_verified") is not True:
        raise HTTPException(status_code=401, detail="Google tidak mengonfirmasi email akun ini.")

    user = db.query(models.User).filter(func.lower(models.User.email) == email).first()
    if not user:
        raise HTTPException(status_code=404, detail="Email Google belum terdaftar di Smart Lock. Daftar akun terlebih dahulu menggunakan email yang sama.")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Akun Smart Lock tidak aktif.")

    token = auth.create_access_token({"sub": user.id, "role": user.role.value})
    return {"access_token": token, "token_type": "bearer", "user": user}


@router.get("/me", response_model=schemas.UserOut)
def get_me(current_user: models.User = Depends(auth.get_current_user)):
    return current_user


@router.get("/users", response_model=list[schemas.UserOut])
def list_users(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_owner),
):
    """Daftar semua user yang sudah register di sistem, khusus owner.
    Dipakai dashboard biar owner bisa PILIH user dari daftar (misal buat
    grant permission / daftarkan kartu NFC ke email tertentu), bukan harus
    ngetik/ngapal email orang lain secara manual."""
    return db.query(models.User).order_by(models.User.name.asc()).all()


@router.get("/me/face-profile")
def my_face_profile(response: Response, db: Session = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    response.headers["Cache-Control"] = "no-store"
    profile = db.get(models.FaceProfile, current_user.id)
    if not profile:
        raise HTTPException(status_code=404, detail="Wajah belum terdaftar. Minta owner mendaftarkan wajah Anda melalui Pengaturan.")
    return {"model_version": profile.model_version, "descriptors": profile.descriptors,
            "user_id": current_user.id, "user_name": current_user.name}


@router.get('/me/face-profile/status')
def my_face_status(response: Response, db: Session = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    response.headers['Cache-Control'] = 'no-store'
    profile = db.query(models.FaceProfile.updated_at).filter(models.FaceProfile.user_id == current_user.id).first()
    return {'registered': profile is not None, 'updated_at': profile.updated_at if profile else None}


@router.put("/users/{user_id}/face-profile")
def register_face_profile(user_id: str, payload: schemas.FaceProfileInput, db: Session = Depends(get_db), current_user: models.User = Depends(auth.require_owner)):
    target = db.get(models.User, user_id)
    if not target or not target.is_active:
        raise HTTPException(status_code=404, detail="Akun aktif tidak ditemukan")
    profile = db.get(models.FaceProfile, user_id)
    if not profile:
        profile = models.FaceProfile(user_id=user_id, registered_by=current_user.id)
        db.add(profile)
    profile.descriptors = payload.descriptors
    profile.model_version = payload.model_version
    profile.registered_by = current_user.id
    profile.updated_at = datetime.utcnow()
    db.commit()
    return {"status": "registered", "user_id": user_id}


@router.put('/me/face-profile')
def register_my_face(payload: schemas.FaceProfileInput, db: Session = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    if current_user.role != models.UserRole.owner:
        approved = db.query(models.Permission).join(models.Device, models.Permission.device_id == models.Device.id).filter(
            models.Permission.user_id == current_user.id, models.Permission.can_unlock.is_(True),
            models.Permission.allow_face.is_(True), models.Device.face_verification_enabled.is_(True),
        ).first()
        if not approved:
            raise HTTPException(status_code=403, detail='Owner belum mengizinkan pendaftaran/akses wajah pada perangkat Anda')
    # Bind to the authenticated user; never accept a target user supplied by the client.
    return register_face_profile(current_user.id, payload, db, current_user)


@router.delete("/users/{user_id}/face-profile", status_code=204)
def delete_face_profile(user_id: str, db: Session = Depends(get_db), current_user: models.User = Depends(auth.require_owner)):
    profile = db.get(models.FaceProfile, user_id)
    if profile:
        db.delete(profile)
        db.commit()
