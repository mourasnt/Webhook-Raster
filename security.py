import hashlib
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from redis.asyncio import Redis

from config import settings

logger = logging.getLogger(__name__)

# Timezone de São Paulo
SP_TZ = ZoneInfo(settings.TIMEZONE)


def generate_event_id(body: bytes) -> str:
    """
    Gera um event_id determinístico via SHA256 dos bytes brutos do request body.
    Mesmo payload = mesmo hash = detectado como duplicado.
    """
    return hashlib.sha256(body).hexdigest()


async def check_idempotency(redis: Redis, event_id: str) -> bool:
    """
    Verifica se o evento já foi processado usando SET NX (atômico).

    Returns:
        True  — evento é NOVO (inserido no Redis com sucesso)
        False — evento é DUPLICADO (já existia no Redis)
    """
    key = f"webhook:event:{event_id}"

    # SET key "1" NX EX ttl — seta apenas se não existe, com TTL
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
    """
    Valida se o timestamp do payload está dentro da janela permitida.

    Compara contra o horário atual no timezone de São Paulo.
    Rejeita eventos com timestamp mais antigo que TIMESTAMP_MAX_AGE_SECONDS.

    Args:
        timestamp_str: Timestamp ISO 8601 do payload (opcional).

    Returns:
        True  — timestamp válido ou ausente (campo ainda não enviado pelo remetente)
        False — timestamp fora da janela permitida
    """
    if not timestamp_str:
        # Campo ainda não enviado pelo remetente — aceitar por enquanto
        return True

    try:
        # Parsear timestamp ISO 8601
        event_time = datetime.fromisoformat(timestamp_str)

        # Se não tem timezone, assumir São Paulo
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
    """Retorna o datetime atual no timezone de São Paulo."""
    return datetime.now(SP_TZ)


def now_sp_str() -> str:
    """Retorna o datetime atual no timezone de São Paulo como string ISO 8601."""
    return now_sp().strftime("%Y-%m-%d %H:%M:%S %Z")
