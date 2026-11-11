from datetime import datetime, timezone, time
from typing import Optional
import re
import math
from pydantic import BaseModel, EmailStr, Field, field_validator

from app.models import (
    UserRole,
    DeviceStatus,
    LockStatus,
    DoorState,
    AccessMethod,
    AccessResult,
    GuestAccessStatus,
)


# ---------- Auth ----------
class UserRegister(BaseModel):
    name: str
    email: EmailStr
    password: str = Field(min_length=6)

    @field_validator('password', mode='before')
    @classmethod
    def validate_registration_password(cls, value):
        if not isinstance(value, str):
            return value
        missing = []
        if len(value) < 6:
            missing.append('minimal 6 karakter')
        if not re.search(r'[A-Z]', value):
            missing.append('1 huruf besar (A–Z)')
        if not re.search(r'[a-z]', value):
            missing.append('1 huruf kecil (a–z)')
        if not re.search(r'[0-9]', value):
            missing.append('1 angka (0–9)')
        if missing:
            raise ValueError('Password belum memenuhi syarat: ' + ', '.join(missing) + '.')
        return value


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class FaceProfileInput(BaseModel):
    model_config = {"protected_namespaces": ()}
    descriptors: list[list[float]] = Field(min_length=1, max_length=3)
    model_version: str = "face-api-1.7.15"

    @field_validator("model_version")
    @classmethod
    def validate_model(cls, value):
        if value != "face-api-1.7.15":
            raise ValueError("Model wajah tidak didukung")
        return value

    @field_validator("descriptors")
    @classmethod
    def validate_descriptors(cls, samples):
        if len(samples) not in (1, 3):
            raise ValueError('Gunakan satu referensi foto atau tiga referensi pendaftaran lama')
        for sample in samples:
            if len(sample) != 128 or any(not math.isfinite(v) or abs(v) > 2 for v in sample):
                raise ValueError("Descriptor wajah harus berisi 128 angka finite")
            if not 0.5 <= math.sqrt(sum(v * v for v in sample)) <= 2:
                raise ValueError("Descriptor wajah tidak valid")
        for sample in samples[1:]:
            if math.sqrt(sum((a - b) ** 2 for a, b in zip(samples[0], sample))) > 0.4:
                raise ValueError("Sampel harus berasal dari wajah yang sama")
        return samples


class UserOut(BaseModel):
    id: str
    name: str
    email: EmailStr
    role: UserRole
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: Optional["UserOut"] = None  # dikirim sekalian biar client (web/app) gak perlu panggil GET /auth/me terpisah abis login


# ---------- Device ----------
def _validate_device_code(value: str) -> str:
    """Normalisasi kode device yang juga dipakai sebagai segmen topic MQTT."""
    cleaned = value.strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,50}", cleaned):
        raise ValueError("device_code hanya boleh berisi huruf, angka, '-' atau '_' (maksimal 50 karakter)")
    return cleaned


class DeviceCreate(BaseModel):
    device_code: str
    name: str
    location: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    geofence_radius_m: Optional[float] = 100

    @field_validator("device_code")
    @classmethod
    def validate_code(cls, value: str) -> str:
        return _validate_device_code(value)


class DeviceCodeUpdate(BaseModel):
    device_code: str = Field(min_length=1, max_length=50)

    @field_validator("device_code")
    @classmethod
    def validate_code(cls, value: str) -> str:
        return _validate_device_code(value)


class DeviceOut(BaseModel):
    id: str
    device_code: str
    owner_name: Optional[str] = None
    can_use_face: bool = False
    can_use_nfc: bool = False
    can_use_quick: bool = False
    simulated: bool = False
    name: str
    location: Optional[str]
    status: DeviceStatus
    lock_status: LockStatus
    door_state: DoorState
    battery_level: Optional[float]
    latitude: Optional[float]
    longitude: Optional[float]
    geofence_radius_m: Optional[float]
    access_window_enabled: bool = True
    access_start_time: time = time(7, 0)
    access_end_time: time = time(17, 0)
    face_verification_enabled: bool
    nfc_verification_enabled: bool
    last_seen: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


# ---------- Unlock & Access Log ----------
class UnlockRequest(BaseModel):
    """Body opsional. Kalau device punya geofence diset, latitude/longitude WAJIB
    diisi -- kalau device gak punya geofence, body ini boleh dikosongkan sama sekali."""
    latitude: Optional[float] = Field(default=None, ge=-90, le=90, allow_inf_nan=False)
    longitude: Optional[float] = Field(default=None, ge=-180, le=180, allow_inf_nan=False)
    accuracy_m: Optional[float] = Field(default=None, ge=0, allow_inf_nan=False)
    face_verified: Optional[bool] = None  # hasil face match dari client (Opsi A: client-trust, lihat README)
    nfc_card_uid: Optional[str] = None  # UID kartu/tag NFC yang dibaca HP (fitur NFC bawaan HP, bukan hardware reader terpisah)


class DeviceAccessScheduleUpdate(BaseModel):
    enabled: bool = True
    start_time: time
    end_time: time

    @field_validator("end_time")
    @classmethod
    def validate_window(cls, v: time, info) -> time:
        start = info.data.get("start_time")
        if start is not None and v == start:
            raise ValueError("Jam buka dan tutup tidak boleh sama")
        return v


class DeviceLocationUpdate(BaseModel):
    latitude: float
    longitude: float
    geofence_radius_m: float = Field(default=100, gt=0)


class UnlockResponse(BaseModel):
    transaction_id: str
    status: str
    message: str
    simulated: bool = False


class AccessLogOut(BaseModel):
    id: str
    device_id: str
    user_id: Optional[str]
    method: AccessMethod
    result: AccessResult
    transaction_id: Optional[str]
    latitude: Optional[float]
    longitude: Optional[float]
    accuracy_m: Optional[float]
    note: Optional[str]
    timestamp: datetime

    class Config:
        from_attributes = True


# ---------- Permissions ----------
class PermissionCreate(BaseModel):
    device_id: str
    user_email: EmailStr  # owner cari user lewat email, gak perlu tau user_id
    can_unlock: bool = True
    allow_face: bool = True
    allow_nfc: bool = True
    allow_quick: bool = False
    face_match_threshold: float = Field(default=0.45, ge=0.30, le=0.55, allow_inf_nan=False)
    schedule_start: Optional[str] = None  # format "HH:MM", kosong = tanpa batas jadwal
    schedule_end: Optional[str] = None
    allow_outside_schedule: bool = False


class PermissionUpdate(BaseModel):
    can_unlock: Optional[bool] = None
    allow_face: Optional[bool] = None
    allow_nfc: Optional[bool] = None
    allow_quick: Optional[bool] = None
    face_match_threshold: Optional[float] = Field(default=None, ge=0.30, le=0.55, allow_inf_nan=False)
    schedule_start: Optional[str] = None
    schedule_end: Optional[str] = None
    allow_outside_schedule: Optional[bool] = None


class PermissionOut(BaseModel):
    id: str
    user_id: str
    user_name: str
    user_email: str
    device_id: str
    can_unlock: bool
    allow_face: bool = True
    allow_nfc: bool = True
    allow_quick: bool = False
    face_match_threshold: float = 0.45
    allow_outside_schedule: bool = False
    schedule_start: Optional[str]
    schedule_end: Optional[str]
    granted_by: str
    created_at: datetime


# ---------- NFC Cards ----------
class NfcCardCreate(BaseModel):
    device_id: str
    card_uid: str
    label: str = Field(min_length=1, max_length=100)
    user_email: Optional[EmailStr] = None  # opsional, kalau mau dikaitkan ke user tertentu buat audit

    @field_validator('card_uid')
    @classmethod
    def validate_uid(cls, value):
        value = value.strip().upper()
        if not re.fullmatch(r'[A-Z0-9:_-]{1,64}', value):
            raise ValueError('UID kartu harus 1–64 karakter huruf/angka, titik dua, garis bawah atau tanda hubung')
        return value


class GeofenceCheck(BaseModel):
    latitude: float = Field(ge=-90, le=90, allow_inf_nan=False)
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False)
    accuracy_m: float = Field(ge=0, allow_inf_nan=False)


class NfcCardUpdate(BaseModel):
    label: Optional[str] = None
    is_active: Optional[bool] = None
    user_email: Optional[EmailStr] = None
    clear_user: bool = False


class NfcCardOut(BaseModel):
    id: str
    device_id: str
    card_uid: str
    label: str
    user_id: Optional[str]
    user_name: Optional[str] = None
    user_email: Optional[EmailStr] = None
    is_active: bool
    created_by: str
    created_at: datetime

    class Config:
        from_attributes = True


# ---------- Guest Access (QR tamu) ----------
class GuestAccessCreate(BaseModel):
    device_id: str
    guest_name: str
    valid_from: datetime
    valid_until: datetime
    max_uses: int = Field(default=1, ge=1)
    pin_otp: Optional[str] = None  # kosong = backend generate otomatis 6 digit

    @field_validator("valid_from", "valid_until")
    @classmethod
    def normalize_to_naive_utc(cls, v: datetime) -> datetime:
        """
        Kalau client kirim datetime dengan info timezone (mis. diakhiri "Z" atau
        "+07:00"), konversi dulu ke UTC lalu buang info timezone-nya -- supaya
        hasil akhirnya SELALU representasi UTC yang polos (naive), konsisten
        dengan datetime.utcnow() yang dipakai di tempat lain (mis.
        _compute_effective_status). Tanpa ini, database (khususnya kolom
        TIMESTAMP WITHOUT TIME ZONE di Postgres) bisa diam-diam ikut
        meng-convert ke timezone lokal server saat insert, menggeser jam
        beberapa jam dari yang dimaksud client.
        """
        if v.tzinfo is not None:
            v = v.astimezone(timezone.utc).replace(tzinfo=None)
        return v


class GuestAccessOut(BaseModel):
    id: str
    device_id: str
    guest_name: str
    token: str
    pin_otp: Optional[str]
    valid_from: datetime
    valid_until: datetime
    max_uses: int
    use_count: int
    status: GuestAccessStatus
    created_by: str
    created_at: datetime

    class Config:
        from_attributes = True


class GuestRedeemRequest(BaseModel):
    # PIN hanya diwajibkan untuk QR yang dapat dipakai lebih dari sekali.
    pin_otp: Optional[str] = None


class GuestAccessPublicOut(BaseModel):
    """Info publik QR tamu. Tidak pernah membocorkan PIN; hanya memberi tahu
    apakah halaman perlu meminta PIN berdasarkan batas pemakaian."""
    guest_name: str
    device_name: str
    status: GuestAccessStatus
    valid_until: datetime
    requires_pin: bool = False


# ---------- Hardware (ESP32 -> Backend), sesuai FIRMWARE_INTEGRATION_ADDENDUM_UPDATE.md ----------
class HardwareAckIn(BaseModel):
    status: str  # firmware saat ini cuma kirim "success"


class HardwareHeartbeatIn(BaseModel):
    status: str  # "online"
    mqtt_connected: bool
    uptime_ms: int
    battery_level: Optional[float] = None  # persen 0-100, dari voltage divider LiPo. None kalau device gak pakai baterai (misal cuma adaptor).


class HardwareEventIn(BaseModel):
    event_type: str  # "door_state_changed"
    door_state: Optional[str] = None  # "open" | "closed"
    timestamp_device_ms: Optional[int] = None


class HardwareNfcVerifyIn(BaseModel):
    card_uid: str  # ID yang dibaca PN532 -- bisa dari kartu fisik (UID asli) ATAU dari HP (ID tetap hasil APDU exchange dengan HCE Service di app)


class HardwareNfcVerifyOut(BaseModel):
    unlock: bool
    message: str


class HardwareFaceVerifyIn(BaseModel):
    # ID user yang DIKENALI oleh modul/app face recognition.
    # Model face matching tetap dijalankan di client/hardware pada prototype ini;
    # backend hanya menerima hasil verifikasi dan mengikatnya ke user yang dipilih.
    user_id: str
    face_verified: bool = False
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    accuracy_m: Optional[float] = None


class HardwareFaceVerifyOut(BaseModel):
    unlock: bool
    message: str
