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

    # Postgres (async)
    DATABASE_URL: str = os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@postgres:5432/webhooks",
    )

    # LGPD — Retenção de logs (Art. 15/16)
    LOG_RETENTION_DAYS: int = int(os.environ.get("LOG_RETENTION_DAYS", "30"))

    # LGPD — Audit trail (Art. 37)
    AUDIT_LOG_FILE: str = os.environ.get("AUDIT_LOG_FILE", "logs/audit.json")

    # LGPD — Chave de criptografia Fernet (Art. 46)
    # Gerar com: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    ENCRYPTION_KEY: str = os.environ.get("ENCRYPTION_KEY", "")

    # Google Drive — Upload de documentos base64
    GOOGLE_DRIVE_FOLDER_ID: str = os.environ.get("GOOGLE_DRIVE_FOLDER_ID", "")
    GOOGLE_CREDENTIALS_FILE: str = os.environ.get("GOOGLE_CREDENTIALS_FILE", "credentials.json")


settings = Settings()
