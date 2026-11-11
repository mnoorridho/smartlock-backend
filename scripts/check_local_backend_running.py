"""Smoke-test the opt-in local server, then remove only its temporary test records."""
import json
from pathlib import Path
import secrets
import sqlite3
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ORIGIN = "http://127.0.0.1:8000"
DATABASE = Path(__file__).resolve().parent.parent / ".local" / "smartlock-test.sqlite3"

def request(method, path, payload=None, token=None, form=False):
    headers = {}
    if token:
        headers["Authorization"] = "Bearer " + token
    data = None
    if payload is not None:
        data = (urlencode(payload) if form else json.dumps(payload)).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded" if form else "application/json"
    with urlopen(Request(ORIGIN + path, data=data, headers=headers, method=method), timeout=15) as response:
        return json.load(response)

info = request("GET", "/local-test/info")
assert info['mode'] == 'local-test' and info['database'] == 'sqlite' and info['hardware_commands_enabled'] is False, "This check must only run against the isolated test server."
assert DATABASE.is_file()
suffix = secrets.token_hex(5)
password = secrets.token_urlsafe(20)
emails = [f"smoke-{suffix}-{role}@example.com" for role in ("owner", "user")]
user_ids = []
device_id = None
try:
    with sqlite3.connect(DATABASE) as connection:
        if connection.execute("SELECT COUNT(*) FROM users").fetchone()[0]:
            raise RuntimeError("Initial smoke check requires an empty local test database; existing accounts are left untouched.")
    users = []
    for role, email in zip(("owner", "user"), emails):
        result = request("POST", "/auth/register", {"name": "Temporary backend check", "email": email, "password": password})
        user_ids.append(result["id"])
        assert result["role"] == role
        token = request("POST", "/auth/login", {"username": email, "password": password}, form=True)["access_token"]
        assert request("GET", "/auth/me", token=token)["id"] == result["id"]
        users.append(token)
    assert request("GET", "/devices/", token=users[1]) == []
    device = request("POST", "/devices/", {"device_code": "CHECK-" + suffix, "name": "Temporary backend check"}, token=users[0])
    device_id = device["id"]
    request("POST", "/permissions/", {"device_id": device_id, "user_email": emails[1], "can_unlock": True, "allow_face": True, "allow_nfc": True, "allow_quick": False}, token=users[0])
    allowed = request("GET", "/devices/", token=users[1])
    assert len(allowed) == 1 and allowed[0]["id"] == device_id
    assert allowed[0]["can_use_quick"] is False
    assert request("GET", "/auth/me/face-profile/status", token=users[1])["registered"] is False
    print("PASS: real HTTP registration/login, owner/user roles, approved devices, quick-access restriction and face profile status. No unlock commands sent.")
finally:
    with sqlite3.connect(DATABASE) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        if device_id:
            connection.execute("DELETE FROM permissions WHERE device_id=?", (device_id,))
            connection.execute("DELETE FROM devices WHERE id=?", (device_id,))
        for account_id, email in zip(user_ids, emails):
            connection.execute("DELETE FROM users WHERE id=? AND email=?", (account_id, email))
    print("Temporary test records removed; register your own first owner account.")
