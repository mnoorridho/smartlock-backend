"""
Endpoint yang dipanggil ESP32 lewat HTTP, sesuai FIRMWARE_INTEGRATION_ADDENDUM_UPDATE.md.

Beda dari desain awal: konfirmasi command, heartbeat, dan event pintu TIDAK lewat
MQTT publish balik dari ESP32, tapi lewat HTTP POST ke sini. MQTT cuma dipakai satu
arah (backend -> ESP32) untuk mengirim command.

Identifikasi device dipakai lewat header X-Device-Uid (dicocokkan ke devices.device_code).

CATATAN KEAMANAN: dokumen firmware nyebut header X-Device-Secret juga selalu dikirim,
tapi validasinya belum diimplementasikan di sini (belum ada kolom device_secret di
tabel devices). Untuk sekarang endpoint ini terbuka selama X-Device-Uid cocok dengan
device yang terdaftar -- cukup untuk prototipe/demo, TAPI sebaiknya ditambah validasi
device_secret sebelum dipakai di luar jaringan lokal/lab.
"""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app import models, schemas
from app.geo import haversine_distance_m, DEFAULT_MAX_GPS_ACCURACY_M
from app.access_policy import access_allowed_now, access_window_description, get_user_permission, device_window_is_open

router = APIRouter(prefix="/hardware", tags=["Hardware (ESP32)"])


def get_device_from_header(
    x_device_uid: str = Header(..., alias="X-Device-Uid"),
    db: Session = Depends(get_db),
) -> models.Device:
    device = db.query(models.Device).filter(models.Device.device_code == x_device_uid).first()
    if not device:
        raise HTTPException(
            status_code=404,
            detail=f"Device dengan uid '{x_device_uid}' tidak terdaftar di backend",
        )
    return device


@router.post("/commands/{command_id}/ack")
def command_ack(
    command_id: str,
    payload: schemas.HardwareAckIn,
    device: models.Device = Depends(get_device_from_header),
    db: Session = Depends(get_db),
):
    """
    Dipanggil firmware setelah command unlock selesai dieksekusi.
    command_id di path ini = transaction_id yang backend kirim saat publish command
    (lihat mqtt_client.publish_unlock_command), dipakai untuk mencocokkan baris di
    access_logs yang masih berstatus 'pending'.
    """
    log = (
        db.query(models.AccessLog)
        .filter(models.AccessLog.transaction_id == command_id)
        .first()
    )
    if not log:
        raise HTTPException(
            status_code=404,
            detail="command_id tidak ditemukan di access_logs (mungkin sudah lama/expired)",
        )

    # ACK wajib berasal dari device yang sama dengan device pemilik command.
    if log.device_id != device.id:
        raise HTTPException(status_code=403, detail="command_id bukan milik device ini")

    # ACK dibuat idempotent: retry ESP32 tidak boleh mengubah hasil yang sudah final.
    if log.result != models.AccessResult.pending:
        return {"received": True, "duplicate": True, "status": log.result.value}

    log.result = (
        models.AccessResult.success
        if payload.status.lower() == "success"
        else models.AccessResult.failed
    )
    log.note = f"Dikonfirmasi ESP32 lewat HTTP ACK: status={payload.status}"
    db.commit()

    return {"received": True, "status": log.result.value}


@router.post("/face-verify", response_model=schemas.HardwareFaceVerifyOut)
def face_verify(
    payload: schemas.HardwareFaceVerifyIn,
    device: models.Device = Depends(get_device_from_header),
    db: Session = Depends(get_db),
):
    """Jalur otomatis face recognition.

    Engine face matching berjalan di client/hardware pada prototipe ini. Setelah
    hasil match dikirim sebagai face_verified=true, backend memvalidasi user aktif,
    izin akses, jam operasional pintu, dan geofence (jika diaktifkan), lalu mencatat access log.
    """
    if not device.face_verification_enabled:
        note = "Verifikasi wajah tidak diaktifkan untuk device ini"
        db.add(models.AccessLog(
            id=str(uuid.uuid4()),
            device_id=device.id,
            user_id=payload.user_id,
            method=models.AccessMethod.face,
            result=models.AccessResult.denied,
            note=note,
        ))
        db.commit()
        return {"unlock": False, "message": note}

    user = db.get(models.User, payload.user_id)
    if not user or not user.is_active:
        note = "User hasil face recognition tidak ditemukan atau tidak aktif"
        db.add(models.AccessLog(
            id=str(uuid.uuid4()),
            device_id=device.id,
            user_id=payload.user_id,
            method=models.AccessMethod.face,
            result=models.AccessResult.denied,
            note=note,
        ))
        db.commit()
        return {"unlock": False, "message": note}

    if not payload.face_verified:
        note = "Verifikasi wajah gagal"
        db.add(models.AccessLog(
            id=str(uuid.uuid4()),
            device_id=device.id,
            user_id=user.id,
            method=models.AccessMethod.face,
            result=models.AccessResult.denied,
            note=note,
        ))
        db.commit()
        return {"unlock": False, "message": note}

    permission = None
    if user.role == models.UserRole.owner and device.owner_id != user.id:
        return {"unlock": False, "message": "Owner ini tidak memiliki perangkat tersebut"}
    if user.role != models.UserRole.owner:
        permission = get_user_permission(db, device.id, user.id)
        if not permission or not permission.allow_face:
            note = "Akses wajah ditolak: akun belum diberi izin unlock oleh admin"
            db.add(models.AccessLog(device_id=device.id, user_id=user.id, method=models.AccessMethod.face, result=models.AccessResult.denied, note=note))
            db.commit()
            return {"unlock": False, "message": note}
        if not access_allowed_now(device, permission):
            note = access_window_description(device) + ". Akses wajah di luar jam operasional memerlukan izin khusus admin."
            db.add(models.AccessLog(device_id=device.id, user_id=user.id, method=models.AccessMethod.face, result=models.AccessResult.denied, note=note))
            db.commit()
            return {"unlock": False, "message": note}

    # Untuk face recognition, geofence tetap wajib bila device punya lokasi.
    # Ini berbeda dari NFC: NFC sudah menjadi bukti proximity fisik.
    has_geofence = (
        device.latitude is not None
        and device.longitude is not None
        and device.geofence_radius_m is not None
    )
    if has_geofence:
        if payload.latitude is None or payload.longitude is None:
            note = "Verifikasi wajah ditolak: latitude/longitude wajib karena geofence aktif"
            db.add(models.AccessLog(
                id=str(uuid.uuid4()),
                device_id=device.id,
                user_id=user.id,
                method=models.AccessMethod.face,
                result=models.AccessResult.denied,
                note=note,
            ))
            db.commit()
            return {"unlock": False, "message": note}

        if payload.accuracy_m is not None and payload.accuracy_m > DEFAULT_MAX_GPS_ACCURACY_M:
            note = (
                f"Verifikasi wajah ditolak: akurasi GPS terlalu rendah "
                f"({payload.accuracy_m:.0f}m, maksimal {DEFAULT_MAX_GPS_ACCURACY_M:.0f}m)"
            )
            db.add(models.AccessLog(
                id=str(uuid.uuid4()),
                device_id=device.id,
                user_id=user.id,
                method=models.AccessMethod.face,
                result=models.AccessResult.denied,
                latitude=payload.latitude,
                longitude=payload.longitude,
                accuracy_m=payload.accuracy_m,
                note=note,
            ))
            db.commit()
            return {"unlock": False, "message": note}

        distance_m = haversine_distance_m(
            payload.latitude, payload.longitude, device.latitude, device.longitude
        )
        if distance_m > device.geofence_radius_m:
            note = (
                f"Verifikasi wajah ditolak: di luar radius geofence "
                f"(jarak {distance_m:.0f}m, radius {device.geofence_radius_m:.0f}m)"
            )
            db.add(models.AccessLog(
                id=str(uuid.uuid4()),
                device_id=device.id,
                user_id=user.id,
                method=models.AccessMethod.face,
                result=models.AccessResult.denied,
                latitude=payload.latitude,
                longitude=payload.longitude,
                accuracy_m=payload.accuracy_m,
                note=note,
            ))
            db.commit()
            return {"unlock": False, "message": note}

    success_log = models.AccessLog(
        id=str(uuid.uuid4()),
        device_id=device.id,
        user_id=user.id,
        method=models.AccessMethod.face,
        result=models.AccessResult.success,
        latitude=payload.latitude,
        longitude=payload.longitude,
        accuracy_m=payload.accuracy_m,
        note="Unlock via face recognition (hasil verifikasi dari client/hardware)",
    )
    db.add(success_log)
    db.commit()

    return {
        "unlock": True,
        "message": "Wajah valid, hak akses dan jam operasional terpenuhi. Akses dicatat.",
    }


@router.post("/heartbeat")
def heartbeat(
    payload: schemas.HardwareHeartbeatIn,
    device: models.Device = Depends(get_device_from_header),
    db: Session = Depends(get_db),
):
    """Dipanggil firmware tiap 30 detik selama ESP32 nyala & WiFi tersambung."""
    device.status = (
        models.DeviceStatus.online
        if payload.status.lower() == "online"
        else models.DeviceStatus.offline
    )
    device.last_seen = datetime.utcnow()
    if payload.battery_level is not None:
        device.battery_level = payload.battery_level
    db.commit()
    return {"received": True}


@router.post("/events")
def door_event(
    payload: schemas.HardwareEventIn,
    device: models.Device = Depends(get_device_from_header),
    db: Session = Depends(get_db),
):
    """Dipanggil firmware tiap kali reed switch berubah state (bukan berkala)."""
    if payload.event_type == "door_state_changed" and payload.door_state:
        mapping = {"open": models.DoorState.open, "closed": models.DoorState.closed}
        device.door_state = mapping.get(payload.door_state.lower(), models.DoorState.unknown)
        device.last_seen = datetime.utcnow()
        db.commit()
    return {"received": True}


@router.post("/nfc-verify", response_model=schemas.HardwareNfcVerifyOut)
def nfc_verify(
    payload: schemas.HardwareNfcVerifyIn,
    device: models.Device = Depends(get_device_from_header),
    db: Session = Depends(get_db),
):
    """
    Dipanggil firmware (ESP32 + modul PN532) setiap kali ada HP/kartu yang
    berhasil dibaca lewat modul NFC yang terpasang LANGSUNG di device --
    beda dari flow lama di mana HP membaca NFC lewat fitur bawaannya sendiri
    lalu kirim card_uid lewat endpoint /devices/{id}/unlock (yang perlu
    login user). Endpoint ini dipakai TANPA login user sama sekali, murni
    berdasarkan kredensial device (X-Device-Uid), sama seperti heartbeat.

    Backend TETAP jadi satu-satunya sumber kebenaran -- ESP32 sengaja TIDAK
    diberi daftar kartu valid buat disimpan lokal, supaya kalau owner
    menonaktifkan/menghapus kartu lewat dashboard, efeknya langsung berlaku
    di tap berikutnya tanpa perlu sinkronisasi apa pun ke firmware.

    card_uid di body ini bisa berasal dari:
    - Kartu/tag NFC fisik biasa (UID asli kartunya), ATAU
    - HP yang menjalankan HCE Service (ID TETAP yang sengaja didesain fixed
      oleh aplikasi Flutter lewat pertukaran APDU -- BUKAN UID acak bawaan
      Android, yang berubah tiap tap dan tidak akan pernah cocok).
    Backend tidak perlu tahu/peduli asal-usulnya -- keduanya dicocokkan ke
    kolom nfc_cards.card_uid yang sama persis.
    """
    normalized_uid = payload.card_uid.strip().upper()
    if not normalized_uid:
        raise HTTPException(status_code=422, detail="card_uid tidak boleh kosong")

    if not device.nfc_verification_enabled:
        note = "Verifikasi NFC tidak diaktifkan untuk device ini"
        db.add(models.AccessLog(
            id=str(uuid.uuid4()),
            device_id=device.id,
            user_id=None,
            method=models.AccessMethod.nfc,
            result=models.AccessResult.denied,
            note=note,
        ))
        db.commit()
        return {"unlock": False, "message": note}

    card = (
        db.query(models.NfcCard)
        .filter(
            models.NfcCard.device_id == device.id,
            func.upper(func.trim(models.NfcCard.card_uid)) == normalized_uid,
            models.NfcCard.is_active == True,  # noqa: E712
        )
        .first()
    )
    if not card:
        note = f"Kartu/ID tidak dikenali atau sudah dinonaktifkan (uid: {payload.card_uid})"
        db.add(models.AccessLog(
            id=str(uuid.uuid4()),
            device_id=device.id,
            user_id=None,
            method=models.AccessMethod.nfc,
            result=models.AccessResult.denied,
            note=note,
        ))
        db.commit()
        return {"unlock": False, "message": note}

    if card.user_id:
        card_user = db.get(models.User, card.user_id)
        if not card_user or not card_user.is_active:
            note = "Kartu NFC terdaftar, tetapi akun pemilik kartu sedang tidak aktif"
            db.add(models.AccessLog(
                id=str(uuid.uuid4()),
                device_id=device.id,
                user_id=card.user_id,
                method=models.AccessMethod.nfc,
                result=models.AccessResult.denied,
                note=note,
            ))
            db.commit()
            return {"unlock": False, "message": note}

    if card.user_id:
        card_user = db.get(models.User, card.user_id)
        if not card_user or not card_user.is_active:
            note = "Akun pemilik kartu tidak ditemukan atau tidak aktif"
            db.add(models.AccessLog(device_id=device.id, user_id=card.user_id, method=models.AccessMethod.nfc, result=models.AccessResult.denied, note=note))
            db.commit()
            return {"unlock": False, "message": note}
        if card_user.role != models.UserRole.owner:
            permission = get_user_permission(db, device.id, card_user.id)
            if not permission or not permission.allow_nfc:
                note = "Akses NFC ditolak: pemilik kartu belum diberi izin unlock oleh admin"
                db.add(models.AccessLog(device_id=device.id, user_id=card_user.id, method=models.AccessMethod.nfc, result=models.AccessResult.denied, note=note))
                db.commit()
                return {"unlock": False, "message": note}
            if not access_allowed_now(device, permission):
                note = access_window_description(device) + ". Akses NFC di luar jam operasional memerlukan izin khusus admin."
                db.add(models.AccessLog(device_id=device.id, user_id=card_user.id, method=models.AccessMethod.nfc, result=models.AccessResult.denied, note=note))
                db.commit()
                return {"unlock": False, "message": note}
        elif device.owner_id != card_user.id:
            return {"unlock": False, "message": "Owner kartu tidak memiliki perangkat ini"}
    elif not device_window_is_open(device):
        note = access_window_description(device) + ". Kartu yang belum dikaitkan ke akun tidak dapat digunakan di luar jam operasional."
        db.add(models.AccessLog(device_id=device.id, user_id=None, method=models.AccessMethod.nfc, result=models.AccessResult.denied, note=note))
        db.commit()
        return {"unlock": False, "message": note}

    success_log = models.AccessLog(
        id=str(uuid.uuid4()),
        device_id=device.id,
        user_id=card.user_id,
        method=models.AccessMethod.nfc,
        result=models.AccessResult.success,
        note=f"Unlock via NFC/PN532 (kartu: {card.label}, uid: {normalized_uid})",
    )
    db.add(success_log)
    db.commit()

    return {
        "unlock": True,
        "message": f"NFC valid. Hak akses dan jam operasional terpenuhi untuk kartu {card.label}.",
    }
