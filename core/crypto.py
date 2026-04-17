import hashlib
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from cryptography.fernet import Fernet, InvalidToken

from src.config import settings

logger = logging.getLogger(__name__)

SP_TZ = ZoneInfo(settings.TIMEZONE)

_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        key = settings.ENCRYPTION_KEY
        if not key:
            raise RuntimeError(
                "ENCRYPTION_KEY não configurada. "
                "Gere uma com: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
            )
        _fernet = Fernet(key.encode() if isinstance(key, str) else key)
    return _fernet


FIELDS_TO_ENCRYPT: set[str] = {
    "identification",
    "password",
    "base64",
    "placa",
}


def encrypt_value(value: str) -> str:
    if not value:
        return value
    try:
        f = _get_fernet()
        encrypted = f.encrypt(value.encode("utf-8"))
        return f"ENC::{encrypted.decode('utf-8')}"
    except Exception as e:
        logger.error(f"Erro ao criptografar campo: {e}")
        return "[ENCRYPTION_ERROR]"


def decrypt_value(encrypted_value: str) -> str:
    if not encrypted_value or not encrypted_value.startswith("ENC::"):
        return encrypted_value
    try:
        f = _get_fernet()
        token = encrypted_value[5:]
        decrypted = f.decrypt(token.encode("utf-8"))
        return decrypted.decode("utf-8")
    except InvalidToken:
        logger.error("Chave de descriptografia inválida ou token corrompido")
        return "[DECRYPTION_ERROR]"
    except Exception as e:
        logger.error(f"Erro ao descriptografar: {e}")
        return "[DECRYPTION_ERROR]"


def sanitize_payload(payload: dict) -> dict:
    sanitized: dict = {}

    for key, value in payload.items():
        if key in FIELDS_TO_ENCRYPT and isinstance(value, str) and value:
            sanitized[key] = encrypt_value(value)
        elif isinstance(value, dict):
            sanitized[key] = sanitize_payload(value)
        elif isinstance(value, list):
            sanitized[key] = [
                sanitize_payload(item) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            sanitized[key] = value

    return sanitized


def desanitize_payload(payload: dict) -> dict:
    restored: dict = {}

    for key, value in payload.items():
        if isinstance(value, str) and value.startswith("ENC::"):
            restored[key] = decrypt_value(value)
        elif isinstance(value, dict):
            restored[key] = desanitize_payload(value)
        elif isinstance(value, list):
            restored[key] = [
                desanitize_payload(item) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            restored[key] = value

    return restored


def generate_event_id(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


async def check_idempotency(redis, event_id: str) -> bool:
    key = f"webhook:event:{event_id}"

    result = await redis.set(
        key,
        "1",
        nx=True,
        ex=settings.EVENT_TTL_SECONDS,
    )

    if result:
        logger.debug(f"Evento novo registrado: {event_id[:16]}...")
        return True
    else:
        logger.warning(f"Evento duplicado detectado: {event_id[:16]}...")
        return False


def validate_timestamp(timestamp_str: str | None) -> bool:
    if not timestamp_str:
        return True

    try:
        event_time = datetime.fromisoformat(timestamp_str)

        if event_time.tzinfo is None:
            event_time = event_time.replace(tzinfo=SP_TZ)

        now = datetime.now(SP_TZ)
        age_seconds = abs((now - event_time).total_seconds())

        if age_seconds > settings.TIMESTAMP_MAX_AGE_SECONDS:
            logger.warning(
                f"Timestamp rejeitado: idade={age_seconds:.0f}s "
                f"(máximo={settings.TIMESTAMP_MAX_AGE_SECONDS}s)"
            )
            return False

        return True

    except (ValueError, TypeError) as e:
        logger.warning(f"Timestamp inválido '{timestamp_str}': {e}")
        return False


def now_sp() -> datetime:
    return datetime.now(SP_TZ)


def now_sp_str() -> str:
    return now_sp().strftime("%Y-%m-%d %H:%M:%S %Z")


def normalize_placa(value: str | None) -> str | None:
    import re
    if not value:
        return None
    normalized = re.sub(r"[^A-Za-z0-9]", "", value).upper()
    return normalized or None


def normalize_cpf(value: str | None) -> str | None:
    import re
    if not value:
        return None
    normalized = re.sub(r"\D", "", value)
    return normalized or None


def hash_value(value: str | None) -> str | None:
    if not value:
        return None
    return hashlib.sha256(value.encode("utf-8")).hexdigest()