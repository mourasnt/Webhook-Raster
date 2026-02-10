import os


class Settings:
    """Configurações centralizadas via variáveis de ambiente (Docker)."""

    REDIS_URL: str = os.environ.get("REDIS_URL", "redis://redis:6379/0")
    REDIS_RATE_LIMIT_URL: str = os.environ.get("REDIS_RATE_LIMIT_URL", "redis://redis:6379/1")

    # Idempotência — TTL do cache de event_id (24h)
    EVENT_TTL_SECONDS: int = int(os.environ.get("EVENT_TTL_SECONDS", "86400"))

    # Rate limiting — limite global por IP
    RATE_LIMIT: str = os.environ.get("RATE_LIMIT", "100/minute")

    # Replay protection — janela máxima de timestamp (5 min)
    TIMESTAMP_MAX_AGE_SECONDS: int = int(os.environ.get("TIMESTAMP_MAX_AGE_SECONDS", "300"))

    # Logging
    LOG_LEVEL: str = os.environ.get("LOG_LEVEL", "INFO")

    # Timezone
    TIMEZONE: str = "America/Sao_Paulo"


settings = Settings()
