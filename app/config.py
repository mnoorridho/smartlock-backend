from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql://smartlock_user:password@localhost:5432/smartlock_db"

    # JWT
    jwt_secret_key: str = "change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    # Google Identity Services: Web OAuth Client ID (public, aman dipakai di frontend)
    google_client_id: str = ""
    # Timezone kalender akademik / jadwal. Default Indonesia WIB karena
    # jadwal kuliah disimpan sebagai jam lokal (tanpa timezone).
    app_timezone: str = "Asia/Jakarta"

    # MQTT (HiveMQ Cloud)
    mqtt_broker_host: str = ""
    mqtt_broker_port: int = 8883
    mqtt_username: str = ""
    mqtt_password: str = ""
    mqtt_use_tls: bool = True

    class Config:
        env_file = Path(__file__).resolve().parent.parent / ".env"


settings = Settings()
