"""Create fresh, explicitly labeled phone-test accounts only in the isolated local DB."""
import json
from pathlib import Path
import secrets
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ORIGIN = "http://127.0.0.1:8000"
with urlopen(ORIGIN + "/local-test/info", timeout=5) as response:
    info = json.load(response)
assert info['mode'] == 'local-test' and info['database'] == 'sqlite' and info['hardware_commands_enabled'] is False

import run_local_backend  # Overrides environment only for the dedicated local-test DB.
from app import auth, models
from app.database import SessionLocal

def call(path, token=None, payload=None):
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    if token:
        headers["Authorization"] = "Bearer " + token
    request = Request(ORIGIN + path, data=urlencode(payload).encode() if payload else None, headers=headers)
    with urlopen(request, timeout=10) as response:
        return json.load(response)

accounts = {}
with SessionLocal() as db:
    users = {}
    for role in ("owner", "user"):
        email = f"{role}.uji@example.com"
        if db.query(models.User).filter(models.User.email == email).first():
            email = f"{role}.uji.{secrets.token_hex(3)}@example.com"
        password = role.capitalize() + "-Uji-" + secrets.token_urlsafe(7) + "!"
        user = models.User(name=f"{role.capitalize()} Uji HP", email=email,
                           password_hash=auth.hash_password(password), role=models.UserRole(role))
        db.add(user)
        db.flush()
        users[role] = user
        accounts[role] = {"email": email, "password": password, "id": user.id}
    devices = []
    for index, (name, face_allowed) in enumerate((("Pintu Uji Wajah & GPS", True), ("Pintu Uji NFC Saja", False)), start=1):
        code = f"UJI-HP-0{index}"
        if db.query(models.Device).filter(models.Device.device_code == code).first():
            code += "-" + secrets.token_hex(3)
        device = models.Device(device_code=code, name=name, location="Perangkat uji lokal · titik GPS belum ditetapkan",
            owner_id=users["owner"].id, face_verification_enabled=face_allowed,
            nfc_verification_enabled=True, geofence_radius_m=100, access_window_enabled=False)
        db.add(device)
        db.flush()
        db.add(models.Permission(device_id=device.id, user_id=users["user"].id, granted_by=users["owner"].id,
            can_unlock=True, allow_face=face_allowed, allow_nfc=True, allow_quick=False, allow_outside_schedule=False))
        devices.append({"id": device.id, "name": name, "code": code, "face": face_allowed,
                        "nfc": True, "quick": False, "geofence_radius_m": 100, "gps_center_configured": False})
    db.commit()

for role in ("owner", "user"):
    account = accounts[role]
    token = call("/auth/login", payload={"username": account["email"], "password": account["password"]})["access_token"]
    assert call("/auth/me", token)["role"] == role
    visible = call("/devices/", token)
    assert {item["id"] for item in visible} == {item["id"] for item in devices}
    assert call("/auth/me/face-profile/status", token)["registered"] is False
    if role == "user":
        permitted = {item["id"]: item for item in visible}
        assert permitted[devices[0]["id"]]["can_use_face"] is True
        assert permitted[devices[1]["id"]]["can_use_face"] is False
        assert all(item["can_use_nfc"] is True and item["can_use_quick"] is False for item in visible)

result = {"mode": "local-test", "accounts": accounts, "devices": devices,
          "next_step": "Owner must set geofence center using the phone's real GPS; each person must enroll their own face."}
output = Path(__file__).resolve().parent.parent / ".local" / "phone-test-accounts.json"
output.write_text(json.dumps(result, indent=2), encoding="utf-8")
print(json.dumps(result, indent=2))
print("PASS: account logins, owner/user roles, two approved devices, method permissions and empty face enrollment verified.")
