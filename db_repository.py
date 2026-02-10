import hashlib
import logging
import re
from datetime import timedelta, datetime
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from db_models import WebhookEvent
from lgpd import decrypt_value, desanitize_payload, encrypt_value, sanitize_payload
from security import now_sp

logger = logging.getLogger(__name__)


def _normalize_placa(value: str | None) -> str | None:
    if not value:
        return None
    normalized = re.sub(r"[^A-Za-z0-9]", "", value).upper()
    return normalized or None


def _normalize_cpf(value: str | None) -> str | None:
    if not value:
        return None
    normalized = re.sub(r"\D", "", value)
    return normalized or None


def _hash_value(value: str | None) -> str | None:
    if not value:
        return None
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _extract_placa(payload: dict[str, Any]) -> str | None:
    placa = payload.get("placa")
    return placa if isinstance(placa, str) and placa else None


def _extract_cpf(payload: dict[str, Any]) -> str | None:
    identification = payload.get("identification")
    return identification if isinstance(identification, str) and identification else None


def _serialize_event(event: WebhookEvent) -> dict[str, Any]:
    return {
        "id": event.id,
        "webhook_type": event.webhook_type,
        "received_at": event.received_at.isoformat(),
        "event_id": event.event_id,
        "source_ip": event.source_ip,
        "url": event.url,
        "payload": desanitize_payload(event.payload),
    }


async def save_webhook_event(
    session: AsyncSession,
    webhook_type: str,
    url: str,
    payload: dict[str, Any],
    event_id: str | None,
    received_at: datetime | None,
    source_ip: str | None,
) -> int:
    """Persiste o webhook no Postgres com dados criptografados."""
    safe_payload = sanitize_payload(payload)

    placa = _extract_placa(payload)
    cpf = _extract_cpf(payload)

    placa_norm = _normalize_placa(placa)
    cpf_norm = _normalize_cpf(cpf)

    event = WebhookEvent(
        webhook_type=webhook_type,
        received_at=received_at or now_sp(),
        event_id=event_id,
        source_ip=source_ip,
        url=url,
        payload=safe_payload,
        placa_encrypted=encrypt_value(placa) if placa else None,
        cpf_encrypted=encrypt_value(cpf) if cpf else None,
        placa_hash=_hash_value(placa_norm),
        cpf_hash=_hash_value(cpf_norm),
    )

    session.add(event)
    await session.commit()
    await session.refresh(event)
    return event.id


async def search_by_placa(session: AsyncSession, placa: str) -> list[dict[str, Any]]:
    placa_norm = _normalize_placa(placa)
    placa_hash = _hash_value(placa_norm)
    if not placa_hash:
        return []

    stmt = (
        select(WebhookEvent)
        .where(WebhookEvent.placa_hash == placa_hash)
        .order_by(WebhookEvent.received_at.desc())
    )
    result = await session.execute(stmt)
    events = result.scalars().all()
    return [_serialize_event(event) for event in events]


async def search_by_cpf(session: AsyncSession, cpf: str) -> list[dict[str, Any]]:
    cpf_norm = _normalize_cpf(cpf)
    cpf_hash = _hash_value(cpf_norm)
    if not cpf_hash:
        return []

    stmt = (
        select(WebhookEvent)
        .where(WebhookEvent.cpf_hash == cpf_hash)
        .order_by(WebhookEvent.received_at.desc())
    )
    result = await session.execute(stmt)
    events = result.scalars().all()
    return [_serialize_event(event) for event in events]


async def list_all_placas(session: AsyncSession) -> list[str]:
    stmt = (
        select(WebhookEvent.placa_hash, func.max(WebhookEvent.placa_encrypted))
        .where(WebhookEvent.placa_hash.is_not(None))
        .group_by(WebhookEvent.placa_hash)
    )
    result = await session.execute(stmt)
    placas: list[str] = []
    for _, placa_encrypted in result.all():
        if not placa_encrypted:
            continue
        decrypted = decrypt_value(placa_encrypted)
        if decrypted and not decrypted.startswith("["):
            placas.append(decrypted)

    return sorted(set(placas))


async def list_all_cpfs(session: AsyncSession) -> list[str]:
    stmt = (
        select(WebhookEvent.cpf_hash, func.max(WebhookEvent.cpf_encrypted))
        .where(WebhookEvent.cpf_hash.is_not(None))
        .group_by(WebhookEvent.cpf_hash)
    )
    result = await session.execute(stmt)
    cpfs: list[str] = []
    for _, cpf_encrypted in result.all():
        if not cpf_encrypted:
            continue
        decrypted = decrypt_value(cpf_encrypted)
        if decrypted and not decrypted.startswith("["):
            cpfs.append(decrypted)

    return sorted(set(cpfs))


async def purge_old_db_entries(session: AsyncSession) -> int:
    cutoff = now_sp() - timedelta(days=settings.LOG_RETENTION_DAYS)
    stmt = delete(WebhookEvent).where(WebhookEvent.received_at < cutoff)
    result = await session.execute(stmt)
    await session.commit()
    removed = result.rowcount if result.rowcount is not None else 0
    if removed > 0:
        logger.info(f"Retencao DB: {removed} registros removidos")
    return removed
