import enum
import uuid
from datetime import datetime, time

from sqlalchemy import (
    String, Integer, Boolean, DateTime, Time, ForeignKey, Enum, Text, Float, JSON,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def gen_uuid() -> str:
    return str(uuid.uuid4())


class UserRole(str, enum.Enum):
    owner = "owner"
    user = "user"


class DeviceStatus(str, enum.Enum):
    online = "online"
    offline = "offline"


class LockStatus(str, enum.Enum):
    locked = "locked"
    unlocked = "unlocked"
    unknown = "unknown"


class DoorState(str, enum.Enum):
    """Status fisik pintu dari reed switch (GPIO 4 di firmware) — beda dari LockStatus
    yang merepresentasikan status solenoid. Reed switch cuma tau pintu 'open'/'closed'
    secara fisik, bukan apakah solenoid sedang unlock/lock."""
    open = "open"
    closed = "closed"
    unknown = "unknown"


class GuestAccessStatus(str, enum.Enum):
    active = "active"
    not_started = "not_started"
    used = "used"
    expired = "expired"
    revoked = "revoked"


class AccessMethod(str, enum.Enum):
    password = "password"
    face = "face"
    qr = "qr"
    manual = "manual"
    nfc = "nfc"  # ditambahkan biar unlock via NFC (app maupun PN532) tercatat akurat, bukan ikut "manual"


class AccessResult(str, enum.Enum):
    pending = "pending"
    success = "success"
    failed = "failed"
    denied = "denied"
    timeout = "timeout"


# ---------------------------------------------------------------------------
# users
# ---------------------------------------------------------------------------
class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=gen_uuid)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(150), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.user, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    devices_owned: Mapped[list["Device"]] = relationship(back_populates="owner")
    permissions: Mapped[list["Permission"]] = relationship(
        back_populates="user", foreign_keys="Permission.user_id"
    )


# ---------------------------------------------------------------------------
# devices
# ---------------------------------------------------------------------------
class Device(Base):
    __tablename__ = "devices"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=gen_uuid)
    device_code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)  # e.g. "LOCK001", dipakai di topik MQTT
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    location: Mapped[str] = mapped_column(String(150), nullable=True)
    owner_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False)

    status: Mapped[DeviceStatus] = mapped_column(Enum(DeviceStatus), default=DeviceStatus.offline)
    lock_status: Mapped[LockStatus] = mapped_column(Enum(LockStatus), default=LockStatus.unknown)
    door_state: Mapped[DoorState] = mapped_column(Enum(DoorState), default=DoorState.unknown)
    battery_level: Mapped[float] = mapped_column(Float, nullable=True)
    last_seen: Mapped[datetime] = mapped_column(DateTime, nullable=True)

    latitude: Mapped[float] = mapped_column(Float, nullable=True)
    longitude: Mapped[float] = mapped_column(Float, nullable=True)
    geofence_radius_m: Mapped[float] = mapped_column(Float, nullable=True, default=100)
    access_window_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    access_start_time: Mapped[time] = mapped_column(Time, default=time(7, 0), nullable=False)
    access_end_time: Mapped[time] = mapped_column(Time, default=time(17, 0), nullable=False)
    face_verification_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    nfc_verification_enabled: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    owner: Mapped["User"] = relationship(back_populates="devices_owned")
    permissions: Mapped[list["Permission"]] = relationship(back_populates="device")


# ---------------------------------------------------------------------------
# permissions  (siapa boleh akses device apa)
# ---------------------------------------------------------------------------
class Permission(Base):
    __tablename__ = "permissions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=gen_uuid)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False)
    device_id: Mapped[str] = mapped_column(String, ForeignKey("devices.id"), nullable=False)

    can_unlock: Mapped[bool] = mapped_column(Boolean, default=True)
    allow_face: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    allow_nfc: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    allow_quick: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    face_match_threshold: Mapped[float] = mapped_column(Float, default=0.45, nullable=False)
    allow_outside_schedule: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    schedule_start: Mapped[str] = mapped_column(String(5), nullable=True)  # "HH:MM"
    schedule_end: Mapped[str] = mapped_column(String(5), nullable=True)    # "HH:MM"

    granted_by: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship(back_populates="permissions", foreign_keys=[user_id])
    device: Mapped["Device"] = relationship(back_populates="permissions")


# ---------------------------------------------------------------------------
# guest_access  (QR tamu sementara)
# ---------------------------------------------------------------------------
class GuestAccess(Base):
    __tablename__ = "guest_access"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=gen_uuid)
    token: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    device_id: Mapped[str] = mapped_column(String, ForeignKey("devices.id"), nullable=False)

    guest_name: Mapped[str] = mapped_column(String(100), nullable=False)
    pin_otp: Mapped[str] = mapped_column(String(10), nullable=True)

    valid_from: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    valid_until: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    max_uses: Mapped[int] = mapped_column(Integer, default=1)
    use_count: Mapped[int] = mapped_column(Integer, default=0)

    status: Mapped[GuestAccessStatus] = mapped_column(Enum(GuestAccessStatus), default=GuestAccessStatus.not_started)
    created_by: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    device: Mapped["Device"] = relationship()


# ---------------------------------------------------------------------------
# access_logs  (audit log semua percobaan akses)
# ---------------------------------------------------------------------------
class NfcCard(Base):
    __tablename__ = "nfc_cards"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=gen_uuid)
    device_id: Mapped[str] = mapped_column(String, ForeignKey("devices.id"), nullable=False)
    card_uid: Mapped[str] = mapped_column(String(64), nullable=False)  # UID fisik kartu, mis. "04:A3:B2:C1"
    label: Mapped[str] = mapped_column(String(100), nullable=False)  # mis. "Kartu Ridho", "Kartu Cadangan Lab"
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=True)  # opsional, buat audit
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_by: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    device: Mapped["Device"] = relationship()
    user: Mapped["User"] = relationship(foreign_keys=[user_id])


class FaceProfile(Base):
    __tablename__ = "face_profiles"

    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    descriptors: Mapped[list] = mapped_column(JSON, nullable=False)
    model_version: Mapped[str] = mapped_column(String(50), nullable=False)
    registered_by: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class AccessLog(Base):
    __tablename__ = "access_logs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=gen_uuid)
    device_id: Mapped[str] = mapped_column(String, ForeignKey("devices.id"), nullable=False)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=True)          # null jika guest
    guest_access_id: Mapped[str] = mapped_column(String, ForeignKey("guest_access.id"), nullable=True)

    method: Mapped[AccessMethod] = mapped_column(Enum(AccessMethod), nullable=False)
    result: Mapped[AccessResult] = mapped_column(Enum(AccessResult), nullable=False)
    transaction_id: Mapped[str] = mapped_column(String(64), nullable=True, index=True)

    latitude: Mapped[float] = mapped_column(Float, nullable=True)
    longitude: Mapped[float] = mapped_column(Float, nullable=True)
    accuracy_m: Mapped[float] = mapped_column(Float, nullable=True)  # akurasi GPS (meter) saat percobaan ini, dari client
    note: Mapped[str] = mapped_column(Text, nullable=True)

    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    device: Mapped["Device"] = relationship()
    user: Mapped["User"] = relationship()
