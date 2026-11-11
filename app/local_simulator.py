"""Virtual actuator. Enabled exclusively by the isolated SQLite test launcher."""
from datetime import datetime
from pathlib import Path
import threading
import time


class LocalSimulator:
    enabled = False

    def __init__(self):
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._commands = []
        self._relock = {}
        self._thread = None

    def install(self, engine):
        expected = Path(__file__).resolve().parent.parent / '.local' / 'smartlock-test.sqlite3'
        if engine.dialect.name != 'sqlite' or Path(engine.url.database).resolve() != expected.resolve():
            raise RuntimeError('Simulator hanya boleh memakai database SQLite uji terpisah.')
        self.enabled = True

    def publish(self, code, transaction_id):
        if not self.enabled:
            return False
        with self._lock:
            self._commands.append((code, transaction_id, time.monotonic() + .8, time.monotonic() + 10))
        return True

    def start(self):
        if not self.enabled or self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name='smartlock-local-simulator', daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)

    def _run(self):
        from app.database import SessionLocal
        from app import models
        while not self._stop.is_set():
            try:
                now = time.monotonic()
                with self._lock:
                    due = [c for c in self._commands if c[2] <= now]
                    self._commands = [c for c in self._commands if c[2] > now]
                with SessionLocal() as db:
                    devices = db.query(models.Device).all()
                    for device in devices:
                        device.status = models.DeviceStatus.online
                        device.last_seen = datetime.utcnow()
                        if device.door_state == models.DoorState.unknown:
                            device.door_state = models.DoorState.closed
                        if device.lock_status == models.LockStatus.unknown:
                            device.lock_status = models.LockStatus.locked
                        if device.id in self._relock and now >= self._relock[device.id]:
                            device.lock_status = models.LockStatus.locked
                            del self._relock[device.id]
                    for code, transaction_id, _, expires in due:
                        device = next((d for d in devices if d.device_code == code), None)
                        log = db.query(models.AccessLog).filter_by(transaction_id=transaction_id).first()
                        if device and log and log.device_id == device.id and log.result == models.AccessResult.pending:
                            log.result = models.AccessResult.success
                            log.note = '[SIMULASI] Smartlock virtual berhasil dibuka; tidak ada perangkat fisik.'
                            device.lock_status = models.LockStatus.unlocked
                            self._relock[device.id] = now + 5
                        elif device and log is None and now < expires:
                            # Publish precedes the request's DB commit; retry only this transaction.
                            with self._lock:
                                self._commands.append((code, transaction_id, now + .3, expires))
                    db.commit()
            except Exception:
                # No success is reported if the simulator cannot commit the ACK.
                import logging
                logging.getLogger(__name__).exception('Simulator lokal belum dapat memperbarui status')
            self._stop.wait(.4)


simulator = LocalSimulator()
