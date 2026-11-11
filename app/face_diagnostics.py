"""Bounded metadata-only diagnostics. Never accepts images, descriptors, or GPS coordinates."""
from collections import OrderedDict, deque
from datetime import datetime, timezone
import threading
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class FaceDiagnostic(BaseModel):
    model_config = ConfigDict(extra='forbid')
    client_version: str = Field(max_length=50)
    mode: Literal['enroll', 'unlock']
    stage: Literal['quality', 'identity', 'gps', 'camera', 'success', 'error']
    reason: str = Field(max_length=500)
    face_count: int | None = Field(default=None, ge=0, le=100)
    # Fixed scalar whitelist; embedding arrays and image data are not accepted.
    detector_score: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    image_width: float | None = Field(default=None, ge=0, le=16384, allow_inf_nan=False)
    image_height: float | None = Field(default=None, ge=0, le=16384, allow_inf_nan=False)
    face_width: float | None = Field(default=None, ge=0, le=16384, allow_inf_nan=False)
    face_height: float | None = Field(default=None, ge=0, le=16384, allow_inf_nan=False)
    brightness: float | None = Field(default=None, ge=0, le=255, allow_inf_nan=False)
    sharpness: float | None = Field(default=None, ge=0, le=1e7, allow_inf_nan=False)
    eye_texture: float | None = Field(default=None, ge=0, le=255, allow_inf_nan=False)
    nose_texture: float | None = Field(default=None, ge=0, le=255, allow_inf_nan=False)
    mouth_texture: float | None = Field(default=None, ge=0, le=255, allow_inf_nan=False)
    distance: float | None = Field(default=None, ge=0, le=100, allow_inf_nan=False)
    threshold: float | None = Field(default=None, ge=0, le=100, allow_inf_nan=False)


_records = OrderedDict()
_lock = threading.Lock()


def record(user_id, payload):
    item = {**payload.model_dump(exclude_none=True), 'recorded_at': datetime.now(timezone.utc).isoformat()}
    with _lock:
        if user_id not in _records:
            if len(_records) >= 128:
                _records.popitem(last=False)
            _records[user_id] = deque(maxlen=10)
        _records[user_id].append(item)
        _records.move_to_end(user_id)


def latest(user_id):
    with _lock:
        return list(_records.get(user_id, []))
