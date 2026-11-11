from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas, auth

router = APIRouter(prefix="/permissions", tags=["Permissions"])


def _ensure_owns_device(db: Session, device_id: str, current_user: models.User) -> models.Device:
    device = db.get(models.Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device tidak ditemukan")
    if device.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Anda bukan owner device ini")
    return device


def _to_permission_out(permission: models.Permission, user: models.User) -> schemas.PermissionOut:
    return schemas.PermissionOut(
        id=permission.id,
        user_id=permission.user_id,
        user_name=user.name,
        user_email=user.email,
        device_id=permission.device_id,
        can_unlock=permission.can_unlock,
        allow_face=permission.allow_face, allow_nfc=permission.allow_nfc, allow_quick=permission.allow_quick,
        face_match_threshold=permission.face_match_threshold,
        allow_outside_schedule=permission.allow_outside_schedule,
        schedule_start=permission.schedule_start,
        schedule_end=permission.schedule_end,
        granted_by=permission.granted_by,
        created_at=permission.created_at,
    )


@router.post("/", response_model=schemas.PermissionOut, status_code=201)
def grant_permission(
    payload: schemas.PermissionCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_owner),
):
    """Owner kasih izin akses device tertentu ke user biasa, dicari lewat email."""
    _ensure_owns_device(db, payload.device_id, current_user)

    target_user = db.query(models.User).filter(models.User.email == payload.user_email).first()
    if not target_user:
        raise HTTPException(
            status_code=404,
            detail=f"User dengan email '{payload.user_email}' tidak ditemukan. Pastikan dia sudah register dulu.",
        )

    existing = (
        db.query(models.Permission)
        .filter(
            models.Permission.user_id == target_user.id,
            models.Permission.device_id == payload.device_id,
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=400,
            detail="User ini sudah punya izin untuk device ini. Gunakan PATCH /permissions/{id} untuk mengubah.",
        )

    permission = models.Permission(
        user_id=target_user.id,
        device_id=payload.device_id,
        can_unlock=payload.can_unlock,
        allow_face=payload.allow_face, allow_nfc=payload.allow_nfc, allow_quick=payload.allow_quick,
        face_match_threshold=payload.face_match_threshold,
        allow_outside_schedule=payload.allow_outside_schedule,
        schedule_start=payload.schedule_start,
        schedule_end=payload.schedule_end,
        granted_by=current_user.id,
    )
    db.add(permission)
    db.commit()
    db.refresh(permission)
    return _to_permission_out(permission, target_user)


@router.get("/", response_model=List[schemas.PermissionOut])
def list_permissions(
    device_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_owner),
):
    """List semua izin yang owner ini kelola. Bisa difilter per device lewat ?device_id=..."""
    query = (
        db.query(models.Permission)
        .join(models.Device, models.Permission.device_id == models.Device.id)
        .filter(models.Device.owner_id == current_user.id)
    )
    if device_id:
        query = query.filter(models.Permission.device_id == device_id)

    permissions = query.all()
    return [_to_permission_out(p, p.user) for p in permissions]


@router.patch("/{permission_id}", response_model=schemas.PermissionOut)
def update_permission(
    permission_id: str,
    payload: schemas.PermissionUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_owner),
):
    """Ubah can_unlock atau jadwal akses. Field yang tidak dikirim (null) tidak berubah."""
    permission = db.get(models.Permission, permission_id)
    if not permission:
        raise HTTPException(status_code=404, detail="Permission tidak ditemukan")
    _ensure_owns_device(db, permission.device_id, current_user)

    if payload.can_unlock is not None:
        permission.can_unlock = payload.can_unlock
    for field in ('allow_face', 'allow_nfc', 'allow_quick', 'face_match_threshold'):
        if getattr(payload, field) is not None:
            setattr(permission, field, getattr(payload, field))
    if payload.allow_outside_schedule is not None:
        permission.allow_outside_schedule = payload.allow_outside_schedule
    if payload.schedule_start is not None:
        permission.schedule_start = payload.schedule_start
    if payload.schedule_end is not None:
        permission.schedule_end = payload.schedule_end

    db.commit()
    db.refresh(permission)
    return _to_permission_out(permission, permission.user)


@router.delete("/{permission_id}", status_code=204)
def revoke_permission(
    permission_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_owner),
):
    """Cabut izin akses user ke device tertentu sepenuhnya."""
    permission = db.get(models.Permission, permission_id)
    if not permission:
        raise HTTPException(status_code=404, detail="Permission tidak ditemukan")
    _ensure_owns_device(db, permission.device_id, current_user)

    db.delete(permission)
    db.commit()
    return None
