import os


class Settings:
    REDIS_URL: str = os.environ.get("REDIS_URL", "redis://redis:6379/0")
    REDIS_RATE_LIMIT_URL: str = os.environ.get("REDIS_RATE_LIMIT_URL", "redis://redis:6379/1")

    EVENT_TTL_SECONDS: int = int(os.environ.get("EVENT_TTL_SECONDS", "86400"))

    RATE_LIMIT: str = os.environ.get("RATE_LIMIT", "100/minute")

    TIMESTAMP_MAX_AGE_SECONDS: int = int(os.environ.get("TIMESTAMP_MAX_AGE_SECONDS", "300"))

    LOG_LEVEL: str = os.environ.get("LOG_LEVEL", "INFO")

    TIMEZONE: str = "America/Sao_Paulo"

    DATABASE_URL: str = os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@postgres:5432/webhooks",
    )

    LOG_RETENTION_DAYS: int = int(os.environ.get("LOG_RETENTION_DAYS", "30"))

    AUDIT_LOG_FILE: str = os.environ.get("AUDIT_LOG_FILE", "logs/audit.json")

    ENCRYPTION_KEY: str = os.environ.get("ENCRYPTION_KEY", "")

    GOOGLE_DRIVE_FOLDER_ID: str = os.environ.get("GOOGLE_DRIVE_FOLDER_ID", "")
    GOOGLE_CREDENTIALS_FILE: str = os.environ.get("GOOGLE_CREDENTIALS_FILE", "credentials.json")

    WHATSAPP_ENABLED: bool = os.environ.get("WHATSAPP_ENABLED", "false").lower() == "true"
    WHATSAPP_API_URL: str = os.environ.get("WHATSAPP_API_URL", "http://5.78.121.199:8080")
    WHATSAPP_INSTANCE: str = os.environ.get("WHATSAPP_INSTANCE", "Spots")
    WHATSAPP_API_KEY: str = os.environ.get("WHATSAPP_API_KEY", "")
    WHATSAPP_DESTINATION: str = os.environ.get("WHATSAPP_DESTINATION", "120363102741946139@g.us")


settings = Settings()