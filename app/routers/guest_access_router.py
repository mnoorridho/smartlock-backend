import secrets
import uuid
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas, auth
from app.mqtt_client import mqtt_bridge
from app.access_policy import device_window_is_open, access_window_description

router = APIRouter(prefix="/guest-access", tags=["Guest Access (QR Tamu)"])


def _generate_token() -> str:
    # Token acak, sulit ditebak -- ini yang di-encode jadi QR / link ke tamu
    return secrets.token_urlsafe(32)


def _generate_pin() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"  # PIN 6 digit, mis. "042817"


def _compute_effective_status(guest: models.GuestAccess) -> models.GuestAccessStatus:
    """
    Status disimpan di kolom `status`, tapi status yang PALING BENAR itu hasil
    hitungan real-time (bukan cuma nilai tersimpan), karena "kedaluwarsa" itu
    soal waktu berjalan, bukan event yang dicatat backend. `revoked` adalah
    satu-satunya status yang harus dipercaya dari database apa adanya (karena
    itu keputusan eksplisit owner, bukan hasil hitungan waktu).
    """
    if guest.status == models.GuestAccessStatus.revoked:
        return models.GuestAccessStatus.revoked

    if guest.use_count >= guest.max_uses:
        return models.GuestAccessStatus.used

    now = datetime.utcnow()
    if now < guest.valid_from:
        return models.GuestAccessStatus.not_started
    if now > guest.valid_until:
        return models.GuestAccessStatus.expired

    return models.GuestAccessStatus.active


def _to_guest_out(guest: models.GuestAccess) -> schemas.GuestAccessOut:
    return schemas.GuestAccessOut(
        id=guest.id,
        device_id=guest.device_id,
        guest_name=guest.guest_name,
        token=guest.token,
        pin_otp=guest.pin_otp,
        valid_from=guest.valid_from,
        valid_until=guest.valid_until,
        max_uses=guest.max_uses,
        use_count=guest.use_count,
        status=_compute_effective_status(guest),
        created_by=guest.created_by,
        created_at=guest.created_at,
    )


def _ensure_owns_device(db: Session, device_id: str, current_user: models.User) -> models.Device:
    device = db.get(models.Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device tidak ditemukan")
    if device.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Anda bukan owner device ini")
    return device


# ------------------------------------------------------------------
# Endpoint OWNER (butuh login)
# ------------------------------------------------------------------
@router.post("/", response_model=schemas.GuestAccessOut, status_code=201)
def create_guest_access(
    payload: schemas.GuestAccessCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_owner),
):
    """Owner bikin akses tamu baru -- hasilnya token (buat di-encode jadi QR) + PIN."""
    _ensure_owns_device(db, payload.device_id, current_user)

    if payload.valid_until <= payload.valid_from:
        raise HTTPException(status_code=400, detail="valid_until harus setelah valid_from")

    # QR sekali pakai cukup menjadi token pembuka: tidak ada PIN.
    # QR multi-pakai wajib dilindungi PIN, dibuat otomatis jika owner tidak mengisi.
    if payload.max_uses > 1:
        pin_otp = payload.pin_otp or _generate_pin()
    else:
        pin_otp = None

    guest = models.GuestAccess(
        token=_generate_token(),
        device_id=payload.device_id,
        guest_name=payload.guest_name,
        pin_otp=pin_otp,
        valid_from=payload.valid_from,
        valid_until=payload.valid_until,
        max_uses=payload.max_uses,
        use_count=0,
        status=models.GuestAccessStatus.not_started,  # akan dihitung ulang tiap dibaca, lihat _compute_effective_status
        created_by=current_user.id,
    )
    db.add(guest)
    db.commit()
    db.refresh(guest)
    return _to_guest_out(guest)


@router.get("/", response_model=List[schemas.GuestAccessOut])
def list_guest_access(
    device_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_owner),
):
    query = (
        db.query(models.GuestAccess)
        .join(models.Device, models.GuestAccess.device_id == models.Device.id)
        .filter(models.Device.owner_id == current_user.id)
    )
    if device_id:
        query = query.filter(models.GuestAccess.device_id == device_id)

    guests = query.order_by(models.GuestAccess.created_at.desc()).all()
    return [_to_guest_out(g) for g in guests]


@router.delete("/{guest_access_id}", status_code=204)
def revoke_guest_access(
    guest_access_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_owner),
):
    """Cabut akses tamu sebelum waktunya habis (mis. tamu batal datang)."""
    guest = db.get(models.GuestAccess, guest_access_id)
    if not guest:
        raise HTTPException(status_code=404, detail="Guest access tidak ditemukan")
    _ensure_owns_device(db, guest.device_id, current_user)

    guest.status = models.GuestAccessStatus.revoked
    db.commit()
    return None


@router.delete("/{guest_access_id}/permanent", status_code=204)
def delete_guest_access_permanent(
    guest_access_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_owner),
):
    """Hapus PERMANEN dari database (beda dari revoke_guest_access di atas
    yang cuma soft-delete/ubah status). Dipakai owner buat beres-beres list
    yang sudah lama expired/revoked/used dan tidak perlu disimpan lagi.
    Endpoint ini TIDAK dipakai Flutter app -- khusus dashboard admin."""
    guest = db.get(models.GuestAccess, guest_access_id)
    if not guest:
        raise HTTPException(status_code=404, detail="Guest access tidak ditemukan")
    _ensure_owns_device(db, guest.device_id, current_user)

    # PENTING: kalau akses tamu ini pernah dipakai (ada percobaan unlock
    # tercatat di access_logs yang mereferensi row ini), DB bakal nolak
    # DELETE karena foreign key constraint. Solusinya BUKAN ikut hapus
    # access_logs-nya (itu riwayat penting, harus tetap ada buat audit),
    # tapi cukup putuskan link-nya (set NULL) -- log tetap ada, cuma gak
    # nunjuk ke guest_access yang mau dihapus ini lagi.
    db.query(models.AccessLog).filter(
        models.AccessLog.guest_access_id == guest_access_id
    ).update({models.AccessLog.guest_access_id: None})

    db.delete(guest)
    db.commit()
    return None


# ------------------------------------------------------------------
# Endpoint TAMU (PUBLIK -- sengaja TANPA auth, tamu gak punya akun)
# ------------------------------------------------------------------
@router.get("/{token}", response_model=schemas.GuestAccessPublicOut)
def get_guest_access_preview(token: str, db: Session = Depends(get_db)):
    """
    Info ringkas buat ditampilkan di halaman web publik SEBELUM tamu masukin
    PIN -- sengaja TIDAK menyertakan pin_otp di response ini.
    """
    guest = db.query(models.GuestAccess).filter(models.GuestAccess.token == token).first()
    if not guest:
        raise HTTPException(status_code=404, detail="QR tidak valid atau sudah tidak berlaku")

    device = db.get(models.Device, guest.device_id)
    return schemas.GuestAccessPublicOut(
        guest_name=guest.guest_name,
        device_name=device.name if device else "Perangkat tidak ditemukan",
        status=_compute_effective_status(guest),
        valid_until=guest.valid_until,
        requires_pin=guest.max_uses > 1,
    )


@router.post("/{token}/redeem", response_model=schemas.UnlockResponse)
def redeem_guest_access(
    token: str,
    payload: schemas.GuestRedeemRequest,
    db: Session = Depends(get_db),
):
    """
    Dipanggil dari halaman web publik yang dibuka tamu setelah scan QR
    (QR isinya URL + token ini, sesuai rancangan di dokumen project --
    "QR sementara + PIN/OTP", bukan sekadar QR polos).
    """
    guest = (
        db.query(models.GuestAccess)
        .filter(models.GuestAccess.token == token)
        .with_for_update()
        .first()
    )
    if not guest:
        raise HTTPException(status_code=404, detail="QR tidak valid atau sudah tidak berlaku")

    effective_status = _compute_effective_status(guest)

    if effective_status == models.GuestAccessStatus.revoked:
        raise HTTPException(status_code=403, detail="Akses ini sudah dicabut oleh pemilik")
    if effective_status == models.GuestAccessStatus.not_started:
        raise HTTPException(
            status_code=403,
            detail=f"Akses ini baru berlaku mulai {guest.valid_from.isoformat()}",
        )
    if effective_status == models.GuestAccessStatus.expired:
        raise HTTPException(status_code=403, detail="Akses ini sudah kedaluwarsa")
    if effective_status == models.GuestAccessStatus.used:
        raise HTTPException(status_code=403, detail="Akses ini sudah mencapai batas penggunaan")

    # Multi-pakai wajib PIN. QR sekali pakai tidak menggunakan PIN sama sekali.
    pin_required = guest.max_uses > 1
    if pin_required and (not guest.pin_otp or payload.pin_otp != guest.pin_otp):
        db.add(
            models.AccessLog(
                device_id=guest.device_id,
                guest_access_id=guest.id,
                method=models.AccessMethod.qr,
                result=models.AccessResult.denied,
                note=f"PIN salah untuk tamu '{guest.guest_name}'",
            )
        )
        db.commit()
        raise HTTPException(status_code=403, detail="PIN wajib diisi atau salah")

    device = db.get(models.Device, guest.device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device untuk akses ini tidak ditemukan")

    if not device_window_is_open(device):
        note = access_window_description(device) + ". Akses tamu di luar jam operasional harus dibuka oleh admin." 
        db.add(models.AccessLog(
            device_id=device.id,
            guest_access_id=guest.id,
            method=models.AccessMethod.qr,
            result=models.AccessResult.denied,
            note=note,
        ))
        db.commit()
        raise HTTPException(status_code=403, detail=note)

    transaction_id = str(uuid.uuid4())
    sent = mqtt_bridge.publish_unlock_command(device.device_code, transaction_id)

    # Hanya pemakaian yang berhasil dikirim ke perangkat yang mengurangi kuota.
    # Untuk QR multi-pakai, PIN lama langsung diganti setelah pemakaian sukses;
    # PIN baru hanya dikirim ke dashboard admin melalui endpoint daftar, bukan ke tamu.
    if sent:
        guest.use_count += 1
        if guest.use_count >= guest.max_uses:
            guest.status = models.GuestAccessStatus.used
            guest.pin_otp = None  # PIN terakhir tidak berlaku setelah kuota habis
        elif guest.max_uses > 1:
            previous_pin = guest.pin_otp
            next_pin = _generate_pin()
            while next_pin == previous_pin:
                next_pin = _generate_pin()
            guest.pin_otp = next_pin

    db.add(
        models.AccessLog(
            device_id=device.id,
            guest_access_id=guest.id,
            method=models.AccessMethod.qr,
            result=models.AccessResult.pending if sent else models.AccessResult.failed,
            transaction_id=transaction_id,
            note=(
                f"Tamu '{guest.guest_name}' membuka lewat QR; PIN dirotasi"
                if sent and guest.max_uses > 1 and guest.use_count < guest.max_uses
                else f"Tamu '{guest.guest_name}' membuka lewat QR" if sent
                else f"Perintah QR untuk tamu '{guest.guest_name}' gagal dikirim; kuota dan PIN tidak berubah"
            ),
        )
    )
    db.commit()

    if not sent:
        raise HTTPException(
            status_code=503,
            detail="Gagal mengirim perintah ke device (MQTT broker tidak terhubung); kuota dan PIN tidak berubah",
        )

    return {
        "transaction_id": transaction_id,
        "status": "command_sent",
        "message": f"Selamat datang, {guest.guest_name}! Pintu sedang dibuka.",
    }
