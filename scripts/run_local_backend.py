"""Explicit local test server: separate SQLite data and no physical MQTT commands."""
import os
from pathlib import Path
import secrets
import sys

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))
LOCAL = PROJECT / ".local"
LOCAL.mkdir(exist_ok=True)
DATABASE = LOCAL / "smartlock-test.sqlite3"
SECRET = LOCAL / "test-jwt-secret.txt"
if not SECRET.exists():
    SECRET.write_text(secrets.token_hex(32), encoding="utf-8")

# Process overrides only: never rewrite .env or access the configured PostgreSQL DB.
os.environ["DATABASE_URL"] = "sqlite:///" + DATABASE.as_posix()
os.environ["JWT_SECRET_KEY"] = SECRET.read_text(encoding="utf-8").strip()
os.environ["MQTT_BROKER_HOST"] = ""
os.environ["MQTT_USERNAME"] = ""
os.environ["MQTT_PASSWORD"] = ""

from sqlalchemy import event, inspect, text
from app.database import Base, engine
from app import models  # Register the application tables.

@event.listens_for(engine, "connect")
def foreign_keys(connection, _):
    connection.execute("PRAGMA foreign_keys=ON")

# Only this isolated, opt-in SQLite test database uses create_all.
# Production PostgreSQL continues to use reviewed Alembic migrations.
Base.metadata.create_all(engine)
if 'face_match_threshold' not in {column['name'] for column in inspect(engine).get_columns('permissions')}:
    with engine.begin() as connection:
        connection.execute(text('ALTER TABLE permissions ADD COLUMN face_match_threshold FLOAT NOT NULL DEFAULT 0.45'))
from app.main import app
from app.local_simulator import simulator
from app.mqtt_client import mqtt_bridge
simulator.install(engine)
mqtt_bridge.publish_unlock_command = simulator.publish
app.add_event_handler('startup', simulator.start)
app.add_event_handler('shutdown', simulator.stop)

@app.get("/local-test/info", include_in_schema=False)
def local_test_info():
    return {"mode": "local-test", "database": "sqlite", "hardware_commands_enabled": False, "simulator_enabled": True}

if __name__ == "__main__":
    import argparse
    import uvicorn
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    print("LOCAL TEST: SQLite terpisah; MQTT/smartlock fisik dinonaktifkan.", flush=True)
    print(f"Database uji: {DATABASE}", flush=True)
    uvicorn.run("app.main:app", host=args.host, port=args.port)
