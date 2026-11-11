"""Kebijakan jam akses Smart Lock. Waktu operasional mengikuti WIB (UTC+7)."""
from datetime import datetime, time, timezone, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app import models

WIB = timezone(timedelta(hours=7))

def now_wib_time() -> time:
    return datetime.now(WIB).time().replace(tzinfo=None, microsecond=0)

def is_time_in_window(now: time, start: time, end: time) -> bool:
    """Interval [start, end); mendukung jadwal melewati tengah malam."""
    now = now.replace(tzinfo=None)
    start = start.replace(tzinfo=None)
    end = end.replace(tzinfo=None)
    if start < end:
        return start <= now < end
    if start > end:
        return now >= start or now < end
    return False

def device_window_is_open(device: models.Device, now: Optional[time] = None) -> bool:
    if not getattr(device, "access_window_enabled", True):
        return True
    start = device.access_start_time or time(7, 0)
    end = device.access_end_time or time(17, 0)
    return is_time_in_window(now or now_wib_time(), start, end)

def get_user_permission(db: Session, device_id: str, user_id: str) -> Optional[models.Permission]:
    return (db.query(models.Permission)
            .filter(models.Permission.device_id == device_id,
                    models.Permission.user_id == user_id,
                    models.Permission.can_unlock.is_(True))
            .first())

def access_allowed_now(device: models.Device, permission: Optional[models.Permission] = None, now: Optional[time] = None) -> bool:
    """Admin/owner di-bypass pada route login; user perlu override bila di luar jam global."""
    if device_window_is_open(device, now):
        # Jam operasional global terbuka; batas jam personal (jika diatur) tetap berlaku.
        if permission and permission.schedule_start and permission.schedule_end:
            try:
                start = time.fromisoformat(permission.schedule_start)
                end = time.fromisoformat(permission.schedule_end)
                return is_time_in_window(now or now_wib_time(), start, end)
            except ValueError:
                return False
        return True
    if not permission or not permission.allow_outside_schedule:
        return False
    # Override global diberikan oleh admin; batas jam individual tetap diterapkan bila ada.
    if permission.schedule_start and permission.schedule_end:
        try:
            start = time.fromisoformat(permission.schedule_start)
            end = time.fromisoformat(permission.schedule_end)
            return is_time_in_window(now or now_wib_time(), start, end)
        except ValueError:
            return False
    return True

def access_window_description(device: models.Device) -> str:
    if not getattr(device, "access_window_enabled", True):
        return "Jadwal akses otomatis sedang dinonaktifkan"
    start = (device.access_start_time or time(7, 0)).strftime("%H:%M")
    end = (device.access_end_time or time(17, 0)).strftime("%H:%M")
    return f"Akses pintu hanya dibuka untuk user pada {start}–{end} WIB"
