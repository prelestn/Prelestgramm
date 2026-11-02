"""
Настройки приложения через pydantic-settings.
Все переменные берутся из .env или переменных окружения Railway.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # База данных
    DATABASE_URL: str = "postgresql+asyncpg://user:pass@localhost:5432/prelestgram"

    # Redis
    REDIS_URL: str = "redis://localhost:6379"

    # Телеграм-бот
    TELEGRAM_BOT_TOKEN: str = ""
    ADMIN_CHAT_ID: int = 0

    # JWT
    JWT_SECRET: str = "change_me_in_production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60 * 24 * 30  # 30 дней

    # MinIO (объектное хранилище)
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_BUCKET: str = "prelestgram"

    # TTL кода авторизации (секунды)
    AUTH_CODE_TTL: int = 300  # 5 минут


settings = Settings()
