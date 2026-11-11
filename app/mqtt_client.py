import json
import ssl
import uuid

import paho.mqtt.client as mqtt

from app.config import settings


class MQTTBridge:
    """
    Publisher command MQTT ke ESP32.

    PENTING (lihat FIRMWARE_INTEGRATION_ADDENDUM_UPDATE.md): firmware ESP32 HANYA
    subscribe untuk menerima command lewat MQTT. Konfirmasi balik (ACK), heartbeat,
    dan event pintu dikirim firmware lewat HTTP POST ke endpoint /hardware/*
    (lihat app/routers/hardware_router.py), BUKAN lewat MQTT publish balik.

    Jadi bridge ini di sisi backend sengaja publish-only — tidak subscribe topic
    apapun, beda dari desain awal yang mengasumsikan ESP32 publish status/event
    lewat MQTT juga.
    """

    def __init__(self):
        self.client = mqtt.Client(
            client_id=f"smartlock-backend-{uuid.uuid4().hex[:8]}",
            protocol=mqtt.MQTTv311,
        )
        if settings.mqtt_username:
            self.client.username_pw_set(settings.mqtt_username, settings.mqtt_password)
        if settings.mqtt_use_tls:
            self.client.tls_set(tls_version=ssl.PROTOCOL_TLS_CLIENT)

        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self._connected = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def start(self):
        if not settings.mqtt_broker_host:
            print("[MQTT] MQTT_BROKER_HOST kosong di .env — MQTT bridge TIDAK dijalankan.")
            print("[MQTT] Isi MQTT_BROKER_HOST/USERNAME/PASSWORD di .env untuk mengaktifkan fitur unlock.")
            return
        try:
            self.client.connect(settings.mqtt_broker_host, settings.mqtt_broker_port, keepalive=60)
            self.client.loop_start()
        except Exception as e:
            print(f"[MQTT] Gagal connect ke broker: {e}")

    def stop(self):
        try:
            self.client.loop_stop()
            self.client.disconnect()
        except Exception:
            pass

    @property
    def is_connected(self) -> bool:
        return self._connected

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------
    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self._connected = True
            print("[MQTT] Terhubung ke broker HiveMQ Cloud.")
        else:
            self._connected = False
            print(f"[MQTT] Gagal konek ke broker, return code={rc}")

    def _on_disconnect(self, client, userdata, rc):
        self._connected = False
        print(f"[MQTT] Terputus dari broker (rc={rc}). Auto-reconnect akan dicoba paho-mqtt.")

    # ------------------------------------------------------------------
    # Publish
    # ------------------------------------------------------------------
    def publish_unlock_command(self, device_uid: str, command_id: str) -> bool:
        """
        Kirim command unlock ke ESP32.

        Topic & payload mengikuti FIRMWARE_INTEGRATION_ADDENDUM_UPDATE.md section 3:
          topic   : smartlock/{device_uid}/commands   (plural, bukan /command)
          payload : {"command_id": "...", "action": "unlock"}

        Firmware cuma mengenali action == "unlock" (huruf kecil semua). command_id
        WAJIB diisi valid karena firmware pakai nilai ini apa adanya untuk membentuk
        URL ACK (/hardware/commands/{command_id}/ack) -- kalau kosong, ACK firmware
        akan gagal 404.
        """
        if not settings.mqtt_broker_host:
            return False

        topic = f"smartlock/{device_uid}/commands"
        payload = {
            "command_id": command_id,
            "action": "unlock",
        }
        try:
            result = self.client.publish(topic, json.dumps(payload), qos=1)
            return result.rc == mqtt.MQTT_ERR_SUCCESS
        except Exception as e:
            print(f"[MQTT] Gagal publish command: {e}")
            return False


# Singleton instance dipakai di seluruh aplikasi
mqtt_bridge = MQTTBridge()
