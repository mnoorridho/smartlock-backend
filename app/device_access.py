"""Shared device visibility and method authorization; never trust UI disabled states."""
from fastapi import HTTPException
from app import models
from app.access_policy import get_user_permission, access_allowed_now, access_window_description


def require_device(db, device_id, user, method=None, check_schedule=False):
    device = db.get(models.Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail='Perangkat tidak ditemukan')
    permission = None
    if user.role == models.UserRole.owner:
        if device.owner_id != user.id:
            raise HTTPException(status_code=403, detail='Perangkat ini bukan milik Anda')
    else:
        permission = get_user_permission(db, device_id, user.id)
        if not permission:
            raise HTTPException(status_code=403, detail='Owner belum memberikan hak akses ke perangkat ini')
        if method and not getattr(permission, 'allow_' + method, False):
            raise HTTPException(status_code=403, detail='Metode ' + method + ' tidak diizinkan oleh owner')
        if check_schedule and not access_allowed_now(device, permission):
            raise HTTPException(status_code=403, detail=access_window_description(device))
    if method == 'face' and not device.face_verification_enabled:
        raise HTTPException(status_code=403, detail='Face Unlock dinonaktifkan oleh owner perangkat')
    if method == 'nfc' and not device.nfc_verification_enabled:
        raise HTTPException(status_code=403, detail='Akses NFC dinonaktifkan oleh owner perangkat')
    return device, permission


def device_output(device, user, permission=None):
    from app.schemas import DeviceOut
    from app.local_simulator import simulator
    owner = user.role == models.UserRole.owner
    return DeviceOut.model_validate(device).model_copy(update={
        'owner_name': device.owner.name,
        'simulated': simulator.enabled,
        'can_use_face': bool(device.face_verification_enabled and (owner or permission and permission.allow_face)),
        'can_use_nfc': bool(device.nfc_verification_enabled and (owner or permission and permission.allow_nfc)),
        'can_use_quick': bool(owner or permission and permission.allow_quick),
    })
