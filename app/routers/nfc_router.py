from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app import models, schemas, auth
from app.device_access import require_device

router = APIRouter(prefix="/nfc-cards", tags=["NFC Cards"])


def models_to_nfc_out(card: models.NfcCard, user: Optional[models.User]):
    return schemas.NfcCardOut(
        id=card.id, device_id=card.device_id, card_uid=card.card_uid, label=card.label,
        user_id=card.user_id, user_name=user.name if user else None,
        user_email=user.email if user else None, is_active=card.is_active,
        created_by=card.created_by, created_at=card.created_at,
    )


def _ensure_owns_device(db: Session, device_id: str, current_user: models.User) -> models.Device:
    device = db.get(models.Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device tidak ditemukan")
    if device.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Anda bukan owner device ini")
    return device


@router.post("/", response_model=schemas.NfcCardOut, status_code=201)
def register_nfc_card(
    payload: schemas.NfcCardCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """Owner daftarin kartu NFC baru buat device tertentu. card_uid didapat dari
    hasil scan kartu pertama kali (lihat catatan di README soal alur provisioning)."""
    if current_user.role == models.UserRole.owner:
        _ensure_owns_device(db, payload.device_id, current_user)
    else:
        require_device(db, payload.device_id, current_user, method='nfc')
        if payload.user_email and payload.user_email.lower() != current_user.email.lower():
            raise HTTPException(status_code=403, detail='User hanya boleh mendaftarkan kartu untuk akunnya sendiri')
    normalized_uid = payload.card_uid.strip().upper()
    if not normalized_uid:
        raise HTTPException(status_code=422, detail="card_uid tidak boleh kosong")

    existing = (
        db.query(models.NfcCard)
        .filter(
            models.NfcCard.device_id == payload.device_id,
            func.upper(func.trim(models.NfcCard.card_uid)) == normalized_uid,
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=400, detail="Kartu ini sudah terdaftar untuk device ini")

    user_id = current_user.id if current_user.role != models.UserRole.owner else None
    if payload.user_email and current_user.role == models.UserRole.owner:
        user = db.query(models.User).filter(models.User.email == payload.user_email).first()
        if not user:
            raise HTTPException(status_code=404, detail=f"User dengan email '{payload.user_email}' tidak ditemukan")
        user_id = user.id

    card = models.NfcCard(
        device_id=payload.device_id,
        card_uid=normalized_uid,
        label=payload.label,
        user_id=user_id,
        created_by=current_user.id,
    )
    db.add(card)
    db.commit()
    db.refresh(card)
    return models_to_nfc_out(card, db.get(models.User, card.user_id) if card.user_id else None)


@router.get("/", response_model=List[schemas.NfcCardOut])
def list_nfc_cards(
    device_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    query = db.query(models.NfcCard).join(models.Device, models.NfcCard.device_id == models.Device.id)
    if current_user.role == models.UserRole.owner:
        query = query.filter(models.Device.owner_id == current_user.id)
    else:
        if device_id:
            require_device(db, device_id, current_user, method='nfc')
        query = query.join(models.Permission, models.Permission.device_id == models.Device.id).filter(
            models.NfcCard.user_id == current_user.id, models.Permission.user_id == current_user.id,
            models.Permission.can_unlock.is_(True), models.Permission.allow_nfc.is_(True),
            models.Device.nfc_verification_enabled.is_(True),
        )
    if device_id:
        query = query.filter(models.NfcCard.device_id == device_id)
    cards = query.order_by(models.NfcCard.created_at.desc()).all()
    result = []
    for card in cards:
        user = db.get(models.User, card.user_id) if card.user_id else None
        result.append(models_to_nfc_out(card, user))
    return result


@router.patch("/{card_id}", response_model=schemas.NfcCardOut)
def update_nfc_card(
    card_id: str,
    payload: schemas.NfcCardUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_owner),
):
    """Ubah label, atau nonaktifkan sementara (is_active=false) tanpa hapus permanen."""
    card = db.get(models.NfcCard, card_id)
    if not card:
        raise HTTPException(status_code=404, detail="Kartu NFC tidak ditemukan")
    _ensure_owns_device(db, card.device_id, current_user)

    if payload.label is not None:
        card.label = payload.label
    if payload.is_active is not None:
        card.is_active = payload.is_active

    if payload.clear_user:
        card.user_id = None
    elif payload.user_email is not None:
        user = db.query(models.User).filter(models.User.email == payload.user_email).first()
        if not user:
            raise HTTPException(status_code=404, detail=f"User dengan email '{payload.user_email}' tidak ditemukan")
        if not user.is_active:
            raise HTTPException(status_code=422, detail="User yang dipasangkan ke kartu harus aktif")
        card.user_id = user.id

    db.commit()
    db.refresh(card)
    return models_to_nfc_out(card, db.get(models.User, card.user_id) if card.user_id else None)


@router.delete("/{card_id}", status_code=204)
def delete_nfc_card(
    card_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_owner),
):
    """Hapus kartu permanen (mis. kartu hilang/rusak). Kalau cuma mau nonaktifkan
    sementara, pakai PATCH is_active=false, bukan ini."""
    card = db.get(models.NfcCard, card_id)
    if not card:
        raise HTTPException(status_code=404, detail="Kartu NFC tidak ditemukan")
    _ensure_owns_device(db, card.device_id, current_user)

    db.delete(card)
    db.commit()
    return None
