import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app import models, schemas, auth
from app.mqtt_client import mqtt_bridge
from app.geo import haversine_distance_m, DEFAULT_MAX_GPS_ACCURACY_M
from app.access_policy import access_allowed_now, access_window_description
from app.device_access import require_device, device_output
from app.local_simulator import simulator

router = APIRouter(prefix="/devices", tags=["Devices"])


@router.post("/", response_model=schemas.DeviceOut, status_code=201)
def create_device(
    payload: schemas.DeviceCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_owner),
):
    existing = db.query(models.Device).filter(models.Device.device_code == payload.device_code).first()
    if existing:
        raise HTTPException(status_code=400, detail="device_code sudah dipakai")

    device = models.Device(**payload.model_dump(), owner_id=current_user.id)
    db.add(device)
    db.commit()
    db.refresh(device)
    return device


@router.get("/", response_model=list[schemas.DeviceOut])
def list_devices(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    if current_user.role == models.UserRole.owner:
        return [device_output(d, current_user) for d in db.query(models.Device).filter(models.Device.owner_id == current_user.id).all()]

    # user biasa: hanya device yang dia punya izin
    permissions = {p.device_id: p for p in current_user.permissions if p.can_unlock}
    return [device_output(d, current_user, permissions[d.id]) for d in db.query(models.Device).filter(models.Device.id.in_(permissions)).all()]


@router.patch("/{device_id}/code", response_model=schemas.DeviceOut)
def update_device_code(
    device_id: str,
    payload: schemas.DeviceCodeUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_owner),
):
    """Ubah device_code tanpa menghapus device atau data yang terhubung.

    device_code dipakai untuk header X-Device-Uid dan topic MQTT:
    smartlock/{device_code}/commands. Karena itu nilainya harus sama persis
    dengan DEVICE_UID/topic yang dipakai firmware ESP32.
    """
    device = db.get(models.Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device tidak ditemukan")
    if device.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Anda bukan owner device ini")

    new_code = payload.device_code
    existing = (
        db.query(models.Device)
        .filter(models.Device.device_code == new_code, models.Device.id != device.id)
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail=f"device_code '{new_code}' sudah dipakai device lain")

    device.device_code = new_code
    db.commit()
    db.refresh(device)
    return device


@router.get("/{device_id}", response_model=schemas.DeviceOut)
def get_device(
    device_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    device, permission = require_device(db, device_id, current_user)
    return device_output(device, current_user, permission)


@router.delete("/{device_id}", status_code=204)
def delete_device(
    device_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_owner),
):
    """Hapus device beserta SEMUA data akses yang nempel ke situ (access_logs,
    permissions, nfc_cards, guest_access). Ini beda dari revoke
    guest access (yang cuma hapus satu entry) -- di sini device-nya sendiri
    dihapus total dari sistem, jadi riwayatnya ikut dianggap tidak relevan
    lagi. TIDAK BISA DIBATALKAN. access_logs.device_id itu wajib diisi
    (bukan opsional kayak guest_access_id), makanya di sini pilihannya cuma
    "hapus sekalian" atau "gak bisa dihapus sama sekali" -- bukan
    di-nullify kayak kasus lain."""
    device = db.get(models.Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device tidak ditemukan")
    if device.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Bukan device milik kamu")

    db.query(models.AccessLog).filter(models.AccessLog.device_id == device_id).delete()
    db.query(models.Permission).filter(models.Permission.device_id == device_id).delete()
    db.query(models.NfcCard).filter(models.NfcCard.device_id == device_id).delete()
    db.query(models.GuestAccess).filter(models.GuestAccess.device_id == device_id).delete()

    db.delete(device)
    db.commit()
    return None


@router.patch("/{device_id}/location", response_model=schemas.DeviceOut)
def set_device_location(
    device_id: str,
    payload: schemas.DeviceLocationUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_owner),
):
    """Owner set/ubah titik lokasi + radius geofence device. Begitu ini diisi,
    endpoint unlock WAJIB menerima latitude/longitude dan memvalidasi jaraknya."""
    device = db.get(models.Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device tidak ditemukan")
    if device.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Anda bukan owner device ini")

    device.latitude = payload.latitude
    device.longitude = payload.longitude
    device.geofence_radius_m = payload.geofence_radius_m
    db.commit()
    db.refresh(device)
    return device


@router.patch("/{device_id}/access-schedule", response_model=schemas.DeviceOut)
def update_access_schedule(
    device_id: str,
    payload: schemas.DeviceAccessScheduleUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_owner),
):
    """Atur jam akses pintu global. Owner tetap dapat unlock di luar jadwal."""
    device = db.get(models.Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device tidak ditemukan")
    if device.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Anda bukan owner device ini")
    device.access_window_enabled = payload.enabled
    device.access_start_time = payload.start_time
    device.access_end_time = payload.end_time
    db.commit()
    db.refresh(device)
    return device


@router.delete("/{device_id}/location", response_model=schemas.DeviceOut)
def clear_device_location(
    device_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_owner),
):
    """Matikan verifikasi lokasi buat device ini -- unlock jadi gak perlu kirim lat/lng lagi."""
    device = db.get(models.Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device tidak ditemukan")
    if device.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Anda bukan owner device ini")

    device.latitude = None
    device.longitude = None
    device.geofence_radius_m = None
    db.commit()
    db.refresh(device)
    return device


@router.patch("/{device_id}/face-verification", response_model=schemas.DeviceOut)
def enable_face_verification(
    device_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_owner),
):
    """Owner aktifkan verifikasi wajah buat device ini. Begitu aktif, unlock
    WAJIB menyertakan face_verified=true di body (hasil pengecekan dari client)."""
    device = db.get(models.Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device tidak ditemukan")
    if device.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Anda bukan owner device ini")

    device.face_verification_enabled = True
    db.commit()
    db.refresh(device)
    return device


@router.delete("/{device_id}/face-verification", response_model=schemas.DeviceOut)
def disable_face_verification(
    device_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_owner),
):
    """Owner matikan verifikasi wajah buat device ini."""
    device = db.get(models.Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device tidak ditemukan")
    if device.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Anda bukan owner device ini")

    device.face_verification_enabled = False
    db.commit()
    db.refresh(device)
    return device


@router.patch("/{device_id}/nfc-verification", response_model=schemas.DeviceOut)
def enable_nfc_verification(
    device_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_owner),
):
    """Owner aktifkan verifikasi NFC buat device ini. Begitu aktif, unlock WAJIB
    menyertakan nfc_card_uid yang cocok dengan kartu terdaftar & aktif (lihat /nfc-cards/)."""
    device = db.get(models.Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device tidak ditemukan")
    if device.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Anda bukan owner device ini")

    device.nfc_verification_enabled = True
    db.commit()
    db.refresh(device)
    return device


@router.delete("/{device_id}/nfc-verification", response_model=schemas.DeviceOut)
def disable_nfc_verification(
    device_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_owner),
):
    """Owner matikan verifikasi NFC buat device ini."""
    device = db.get(models.Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device tidak ditemukan")
    if device.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Anda bukan owner device ini")

    device.nfc_verification_enabled = False
    db.commit()
    db.refresh(device)
    return device


@router.post("/{device_id}/unlock", response_model=schemas.UnlockResponse)
def unlock_device(
    device_id: str,
    payload: Optional[schemas.UnlockRequest] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    return _execute_unlock(device_id, payload, db, current_user)


@router.post('/{device_id}/quick-unlock', response_model=schemas.UnlockResponse)
def permitted_quick_unlock(device_id: str, db: Session = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    require_device(db, device_id, current_user, method='quick', check_schedule=True)
    return _execute_unlock(device_id, None, db, current_user, quick=True)


@router.post('/{device_id}/face-precheck')
def face_precheck(device_id: str, payload: schemas.GeofenceCheck, db: Session = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    device, permission = require_device(db, device_id, current_user, method='face', check_schedule=True)
    threshold = permission.face_match_threshold if permission else 0.45
    try:
        configured = device.latitude is not None and device.longitude is not None and device.geofence_radius_m is not None
        if not configured:
            if current_user.role != models.UserRole.owner:
                raise HTTPException(status_code=400, detail='Owner belum mengatur radius geofence. Face Unlock belum dapat digunakan.')
            return {'allowed': True, 'geofence_enabled': False, 'face_match_threshold': threshold}
        if payload.accuracy_m > DEFAULT_MAX_GPS_ACCURACY_M:
            raise HTTPException(status_code=400, detail='GPS kurang akurat. Tunggu sinyal stabil atau pindah ke tempat terbuka.')
        distance = haversine_distance_m(payload.latitude, payload.longitude, device.latitude, device.longitude)
        if distance > device.geofence_radius_m:
            raise HTTPException(status_code=403, detail=f'Anda di luar radius yang diizinkan ({distance:.0f} m; radius {device.geofence_radius_m:.0f} m).')
        return {'allowed': True, 'geofence_enabled': True, 'distance_m': distance, 'face_match_threshold': threshold}
    except HTTPException as error:
        db.add(models.AccessLog(device_id=device.id, user_id=current_user.id, method=models.AccessMethod.face, result=models.AccessResult.denied, latitude=payload.latitude, longitude=payload.longitude, accuracy_m=payload.accuracy_m, note=error.detail))
        db.commit()
        raise


def _execute_unlock(device_id, payload, db, current_user, *, quick=False):
    device = db.get(models.Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device tidak ditemukan")
    if current_user.role == models.UserRole.owner and device.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Anda tidak punya izin membuka device ini")

    # Owner/admin dapat membuka kapan saja. User wajib memiliki izin aktif.
    permission = None
    if current_user.role != models.UserRole.owner:
        permission = (
            db.query(models.Permission)
            .filter(
                models.Permission.user_id == current_user.id,
                models.Permission.device_id == device.id,
                models.Permission.can_unlock == True,  # noqa: E712
            )
            .first()
        )
        if not permission:
            db.add(
                models.AccessLog(
                    device_id=device.id,
                    user_id=current_user.id,
                    method=models.AccessMethod.manual,
                    result=models.AccessResult.denied,
                    note="Tidak memiliki izin unlock untuk device ini",
                )
            )
            db.commit()
            raise HTTPException(status_code=403, detail="Anda tidak punya izin membuka device ini")

    if current_user.role != models.UserRole.owner and not access_allowed_now(device, permission):
        note = access_window_description(device) + ". Minta admin memberi izin akses di luar jam operasional."
        db.add(models.AccessLog(
            device_id=device.id, user_id=current_user.id, method=models.AccessMethod.manual,
            result=models.AccessResult.denied, note=note,
        ))
        db.commit()
        raise HTTPException(status_code=403, detail=note)

    # ------------------------------------------------------------------
    # Verifikasi NFC dicek DULUAN (sebelum geofence) -- soalnya kalau NFC
    # valid, itu sekaligus jadi bukti kedekatan fisik yang JAUH lebih presisi
    # daripada radius geofence GPS (jangkauan NFC cuma beberapa cm, sementara
    # geofence biasanya puluhan-ratusan meter). Jadi kalau NFC-nya valid,
    # geofence gak perlu dicek lagi -- redundan. Geofence tetap wajib kalau
    # yang dipakai buat buktiin identitas itu wajah (yang gak ada hubungannya
    # sama lokasi fisik sama sekali).
    # ------------------------------------------------------------------
    face_verified = payload.face_verified if payload else None
    nfc_card_uid = payload.nfc_card_uid.strip().upper() if payload and payload.nfc_card_uid else None
    lat = payload.latitude if payload else None
    lng = payload.longitude if payload else None
    accuracy_m = payload.accuracy_m if payload else None

    if current_user.role != models.UserRole.owner:
        if quick:
            require_device(db, device_id, current_user, method='quick', check_schedule=True)
        else:
            if nfc_card_uid:
                require_device(db, device_id, current_user, method='nfc', check_schedule=True)
            if face_verified is True:
                require_device(db, device_id, current_user, method='face', check_schedule=True)
                if device.latitude is None or device.longitude is None or device.geofence_radius_m is None:
                    raise HTTPException(status_code=400, detail='Owner belum mengatur radius geofence untuk Face Unlock')
                if accuracy_m is None:
                    raise HTTPException(status_code=400, detail='Face Unlock memerlukan akurasi GPS terbaru')
            if not nfc_card_uid and face_verified is not True:
                raise HTTPException(status_code=403, detail='Gunakan metode akses yang telah disetujui owner')

    nfc_ok = False
    nfc_card = None
    nfc_attempted = bool(device.nfc_verification_enabled and nfc_card_uid)
    if nfc_attempted:
        nfc_card = (
            db.query(models.NfcCard)
            .filter(
                models.NfcCard.device_id == device.id,
                func.upper(func.trim(models.NfcCard.card_uid)) == nfc_card_uid,
                models.NfcCard.is_active == True,  # noqa: E712
            )
            .first()
        )
        nfc_ok = nfc_card is not None

        # Untuk user biasa, kartu harus terkait dengan akun yang sedang login
        # agar identitas pada log akses tidak bisa dipalsukan memakai kartu user lain.
        if nfc_ok and current_user.role != models.UserRole.owner:
            if not nfc_card.user_id:
                note = "Kartu NFC terdaftar tetapi belum dikaitkan dengan akun mahasiswa. Minta owner mengaitkan kartu ke akunmu."
                db.add(models.AccessLog(
                    device_id=device.id,
                    user_id=current_user.id,
                    method=models.AccessMethod.nfc,
                    result=models.AccessResult.denied,
                    note=note,
                ))
                db.commit()
                raise HTTPException(status_code=403, detail=note)
            if nfc_card.user_id != current_user.id:
                note = "Kartu NFC ini terdaftar atas akun lain. Login dengan akun pemilik kartu atau gunakan kartu milikmu."
                db.add(models.AccessLog(
                    device_id=device.id,
                    user_id=current_user.id,
                    method=models.AccessMethod.nfc,
                    result=models.AccessResult.denied,
                    note=note,
                ))
                db.commit()
                raise HTTPException(status_code=403, detail=note)

    # Verifikasi lokasi -- HANYA berlaku kalau device ini punya geofence diset
    # DAN unlock ini gak lolos lewat NFC (NFC valid = proximity udah terbukti
    # lebih akurat, skip geofence).
    has_geofence = (
        device.latitude is not None
        and device.longitude is not None
        and device.geofence_radius_m is not None
    )
    geofence_needed = has_geofence and not nfc_ok and not quick

    if geofence_needed:
        if lat is None or lng is None:
            db.add(
                models.AccessLog(
                    device_id=device.id,
                    user_id=current_user.id,
                    method=models.AccessMethod.manual,
                    result=models.AccessResult.denied,
                    note="Device ini butuh verifikasi lokasi, tapi latitude/longitude tidak dikirim",
                )
            )
            db.commit()
            raise HTTPException(
                status_code=400,
                detail="Device ini butuh verifikasi lokasi. Kirim latitude & longitude di body request (atau pakai NFC, yang membebaskan dari cek lokasi karena udah lebih presisi).",
            )

        # Kalau client kirim accuracy_m dan angkanya buruk, tolak dulu -- GPS yang
        # lagi meleset jauh bisa bikin geofence salah putusan (ketolak padahal
        # deket, atau lolos padahal jauh). Kalau accuracy_m gak dikirim sama
        # sekali, cek ini dilewati (gak semua client punya data ini).
        if accuracy_m is not None and accuracy_m > DEFAULT_MAX_GPS_ACCURACY_M:
            db.add(
                models.AccessLog(
                    device_id=device.id,
                    user_id=current_user.id,
                    method=models.AccessMethod.manual,
                    result=models.AccessResult.denied,
                    latitude=lat,
                    longitude=lng,
                    accuracy_m=accuracy_m,
                    note=f"Akurasi GPS terlalu rendah ({accuracy_m:.0f}m, maksimal {DEFAULT_MAX_GPS_ACCURACY_M:.0f}m)",
                )
            )
            db.commit()
            raise HTTPException(
                status_code=400,
                detail=f"Akurasi GPS terlalu rendah ({accuracy_m:.0f}m). Coba lagi di tempat terbuka atau tunggu sinyal GPS stabil.",
            )

        distance_m = haversine_distance_m(lat, lng, device.latitude, device.longitude)
        if distance_m > device.geofence_radius_m:
            db.add(
                models.AccessLog(
                    device_id=device.id,
                    user_id=current_user.id,
                    method=models.AccessMethod.manual,
                    result=models.AccessResult.denied,
                    latitude=lat,
                    longitude=lng,
                    accuracy_m=accuracy_m,
                    note=f"Di luar radius geofence (jarak {distance_m:.0f}m, radius izin {device.geofence_radius_m:.0f}m)",
                )
            )
            db.commit()
            raise HTTPException(
                status_code=403,
                detail=f"Anda berada di luar radius yang diizinkan (jarak {distance_m:.0f}m, radius {device.geofence_radius_m:.0f}m dari device).",
            )

    # Verifikasi identitas: wajah dan NFC jadi CARA ALTERNATIF (OR), BUKAN dua
    # syarat yang harus dipenuhi bareng (AND). Kalau NFC udah valid (nfc_ok),
    # identitas otomatis terpenuhi juga (gak perlu cek wajah lagi).
    identity_check_needed = not quick and (device.face_verification_enabled or device.nfc_verification_enabled)

    if identity_check_needed and not nfc_ok:
        face_ok = device.face_verification_enabled and face_verified is True

        if not face_ok:
            available = []
            if device.face_verification_enabled:
                available.append("wajah (face_verified: true)")
            if device.nfc_verification_enabled:
                available.append("NFC (nfc_card_uid)")

            if nfc_attempted:
                # User udah coba pakai NFC secara spesifik dan kartunya salah/nonaktif
                # -- kasih pesan spesifik soal itu, bukan pesan umum.
                status_code = 403
                note = f"Kartu/tag NFC tidak dikenal/tidak aktif untuk device ini (uid: {nfc_card_uid})"
                detail = "Kartu/tag NFC tidak dikenali atau tidak aktif untuk device ini."
            else:
                status_code = 400
                note = f"Device ini butuh verifikasi identitas (salah satu: {', '.join(available)}), tapi tidak ada yang terpenuhi"
                detail = f"Device ini butuh verifikasi identitas. Gunakan salah satu: {', '.join(available)}."

            db.add(
                models.AccessLog(
                    device_id=device.id,
                    user_id=current_user.id,
                    method=models.AccessMethod.manual,
                    result=models.AccessResult.denied,
                    latitude=lat,
                    longitude=lng,
                    accuracy_m=accuracy_m,
                    note=note,
                )
            )
            db.commit()
            raise HTTPException(status_code=status_code, detail=detail)

    transaction_id = str(uuid.uuid4())
    sent = mqtt_bridge.publish_unlock_command(device.device_code, transaction_id)

    log = models.AccessLog(
        device_id=device.id,
        user_id=current_user.id,
        method=(models.AccessMethod.nfc if nfc_ok else models.AccessMethod.face if face_verified is True else models.AccessMethod.manual),
        result=models.AccessResult.pending if sent else models.AccessResult.failed,
        transaction_id=transaction_id,
        latitude=lat,
        longitude=lng,
        accuracy_m=accuracy_m,
        note=(
            (
                "Command UNLOCK dikirim via MQTT, menunggu konfirmasi ESP32 "
                f"(metode identitas: {'QUICK' if quick else 'NFC' if nfc_ok else 'FACE' if face_verified is True else 'MANUAL'})"
            )
            if sent and not simulator.enabled
            else '[SIMULASI] Perintah buka dikirim ke smartlock virtual, menunggu konfirmasi.' if sent
            else "Gagal mengirim command: MQTT broker tidak terhubung"
        ),
    )
    db.add(log)
    db.commit()

    if not sent:
        raise HTTPException(
            status_code=503,
            detail="Gagal mengirim perintah ke device (MQTT broker tidak terhubung). Cek konfigurasi MQTT di .env.",
        )

    return {
        "transaction_id": transaction_id,
        "status": "command_sent",
        "message": "Perintah buka dikirim ke perangkat virtual." if simulator.enabled else "Perintah UNLOCK telah dikirim. Menunggu konfirmasi ESP32.",
        "simulated": simulator.enabled,
    }


@router.get("/{device_id}/commands/{transaction_id}")
def command_status(device_id: str, transaction_id: str, db: Session = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    require_device(db, device_id, current_user)
    log = db.query(models.AccessLog).filter(models.AccessLog.device_id == device_id, models.AccessLog.transaction_id == transaction_id).first()
    device = db.get(models.Device, device_id)
    if not log or not device or (log.user_id != current_user.id and device.owner_id != current_user.id):
        raise HTTPException(status_code=404, detail="Perintah tidak ditemukan")
    return {"transaction_id": transaction_id, "result": log.result.value, "simulated": simulator.enabled}


@router.get("/{device_id}/logs", response_model=list[schemas.AccessLogOut])
def get_device_logs(
    device_id: str,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    require_device(db, device_id, current_user)
    query = db.query(models.AccessLog).filter(models.AccessLog.device_id == device_id)
    if current_user.role != models.UserRole.owner:
        query = query.filter(models.AccessLog.user_id == current_user.id)
    return query.order_by(models.AccessLog.timestamp.desc()).limit(max(1, min(limit, 200))).all()
