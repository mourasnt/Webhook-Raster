import logging
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.crypto import (
    decrypt_value,
    desanitize_payload,
    encrypt_value,
    hash_value,
    normalize_cpf,
    normalize_placa,
    now_sp,
    sanitize_payload,
)
from core.database_models import WebhookEvent
from src.config import settings

logger = logging.getLogger(__name__)


def _extract_placa(payload: dict[str, Any]) -> str | None:
    placa = payload.get("placa")
    if placa and isinstance(placa, str):
        return placa

    identification_type = payload.get("identification_type")
    if identification_type == "V" or identification_type == "C":
        identification = payload.get("identification")
        return identification if isinstance(identification, str) and identification else None

    return None


def _extract_cpf(payload: dict[str, Any]) -> str | None:
    identification_type = payload.get("identification_type")

    if identification_type == "V" or identification_type == "C":
        return None

    identification = payload.get("identification")
    return identification if isinstance(identification, str) and identification else None


def _serialize_event(event: WebhookEvent) -> dict[str, Any]:
    return {
        "id": event.id,
        "webhook_type": event.webhook_type,
        "received_at": event.received_at.isoformat(),
        "event_id": event.event_id,
        "source_ip": event.source_ip,
        "payload": desanitize_payload(event.payload),
        "drive_file_id": event.drive_file_id,
        "drive_file_url": event.drive_file_url,
    }


def _serialize_placa_event(event: WebhookEvent) -> dict[str, Any]:
    payload = desanitize_payload(event.payload)

    result = {
        "id": event.id,
        "webhook_type": event.webhook_type,
        "received_at": event.received_at.isoformat(),
        "event_id": event.event_id,
        "source_ip": event.source_ip,
    }

    if event.webhook_type in ("CHECKLIST", "RESULTADOCHECKLIST"):
        result["codchecklist"] = payload.get("codchecklist")

        if event.webhook_type == "RESULTADOCHECKLIST":
            result["resultado"] = payload.get("resultado")
            result["codresultado"] = payload.get("codresultado")
            result["dataexpiracao"] = payload.get("dataexpiracao")
            result["produtos"] = payload.get("produtos", [])

    return result


def _serialize_cpf_event(event: WebhookEvent) -> dict[str, Any]:
    payload = desanitize_payload(event.payload)

    result = {
        "id": event.id,
        "webhook_type": event.webhook_type,
        "received_at": event.received_at.isoformat(),
        "event_id": event.event_id,
        "source_ip": event.source_ip,
    }

    if event.webhook_type == "PESQUISACONCULTA":
        result["pesquisa_id"] = payload.get("id")
        result["identification_type"] = payload.get("identification_type")
        result["situation"] = payload.get("situation")
        result["bond"] = payload.get("bond")
        result["establishment_id"] = payload.get("establishment_id")
        result["expiration_date"] = payload.get("expiration_date")
        result["end_date"] = payload.get("end_date")
        result["reasons"] = payload.get("reasons")
        result["service"] = payload.get("service")

    return result


async def save_webhook_event(
    session: AsyncSession,
    webhook_type: str,
    payload: dict[str, Any],
    event_id: str | None,
    received_at: datetime | None,
    source_ip: str | None,
    drive_file_id: str | None = None,
    drive_file_url: str | None = None,
) -> int:
    safe_payload = sanitize_payload(payload)

    placa = _extract_placa(payload)
    cpf = _extract_cpf(payload)

    placa_norm = normalize_placa(placa)
    cpf_norm = normalize_cpf(cpf)

    event = WebhookEvent(
        webhook_type=webhook_type,
        received_at=received_at or now_sp(),
        event_id=event_id,
        source_ip=source_ip,
        payload=safe_payload,
        placa_encrypted=encrypt_value(placa) if placa else None,
        cpf_encrypted=encrypt_value(cpf) if cpf else None,
        placa_hash=hash_value(placa_norm),
        cpf_hash=hash_value(cpf_norm),
        drive_file_id=drive_file_id,
        drive_file_url=drive_file_url,
    )

    session.add(event)
    await session.commit()
    await session.refresh(event)
    return event.id


async def search_by_placa(session: AsyncSession, placa: str) -> list[dict[str, Any]]:
    placa_norm = normalize_placa(placa)
    placa_hash = hash_value(placa_norm)
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
    cpf_norm = normalize_cpf(cpf)
    cpf_hash = hash_value(cpf_norm)
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


async def list_dados_placas(session: AsyncSession) -> list[dict[str, Any]]:
    stmt = (
        select(WebhookEvent)
        .where(
            WebhookEvent.placa_hash.is_not(None),
            WebhookEvent.webhook_type.in_(["CHECKLIST", "RESULTADOCHECKLIST", "PESQUISACONCULTA"])
        )
        .order_by(WebhookEvent.received_at.desc())
    )
    result = await session.execute(stmt)
    events = result.scalars().all()

    grouped: dict[str, list[WebhookEvent]] = {}
    for event in events:
        if event.placa_hash:
            if event.placa_hash not in grouped:
                grouped[event.placa_hash] = []
            grouped[event.placa_hash].append(event)

    placas_data: list[dict[str, Any]] = []

    for placa_hash, placa_events in grouped.items():
        placa_decrypted = None
        for event in placa_events:
            if event.placa_encrypted:
                placa_decrypted = decrypt_value(event.placa_encrypted)
                if placa_decrypted and not placa_decrypted.startswith("["):
                    break

        if not placa_decrypted:
            continue

        pesquisas = []
        checklists = []
        consultas_veiculo = []

        for event in placa_events:
            if event.webhook_type == "CHECKLIST":
                serialized = _serialize_placa_event(event)
                pesquisas.append(serialized)
            elif event.webhook_type == "RESULTADOCHECKLIST":
                serialized = _serialize_placa_event(event)
                checklists.append(serialized)
            elif event.webhook_type == "PESQUISACONCULTA":
                serialized = _serialize_cpf_event(event)
                consultas_veiculo.append(serialized)

        pesquisas.sort(key=lambda e: e["received_at"], reverse=True)
        checklists.sort(key=lambda e: e["received_at"], reverse=True)
        consultas_veiculo.sort(key=lambda e: e["received_at"], reverse=True)

        total_events = len(pesquisas) + len(checklists) + len(consultas_veiculo)
        last_event_at = max(
            (e.received_at for e in placa_events),
            key=lambda dt: dt,
            default=None
        )

        placas_data.append({
            "placa": placa_decrypted,
            "pesquisas": pesquisas,
            "checklists": checklists,
            "consultas": consultas_veiculo,
            "total_events": total_events,
            "last_event_at": last_event_at.isoformat() if last_event_at else None,
        })

    placas_data.sort(key=lambda p: p["placa"])

    return placas_data


async def list_dados_cpfs(session: AsyncSession) -> list[dict[str, Any]]:
    stmt = (
        select(WebhookEvent)
        .where(
            WebhookEvent.cpf_hash.is_not(None),
            WebhookEvent.webhook_type == "PESQUISACONCULTA"
        )
        .order_by(WebhookEvent.received_at.desc())
    )
    result = await session.execute(stmt)
    events = result.scalars().all()

    grouped: dict[str, list[WebhookEvent]] = {}
    for event in events:
        if event.cpf_hash:
            if event.cpf_hash not in grouped:
                grouped[event.cpf_hash] = []
            grouped[event.cpf_hash].append(event)

    cpfs_data: list[dict[str, Any]] = []

    for cpf_hash, cpf_events in grouped.items():
        cpf_decrypted = None
        for event in cpf_events:
            if event.cpf_encrypted:
                cpf_decrypted = decrypt_value(event.cpf_encrypted)
                if cpf_decrypted and not cpf_decrypted.startswith("["):
                    break

        if not cpf_decrypted:
            continue

        consultas = []
        for event in cpf_events:
            serialized = _serialize_cpf_event(event)
            consultas.append(serialized)

        consultas.sort(key=lambda e: e["received_at"], reverse=True)

        total_events = len(consultas)
        last_event_at = max(
            (e.received_at for e in cpf_events),
            key=lambda dt: dt,
            default=None
        )

        cpfs_data.append({
            "cpf": cpf_decrypted,
            "consultas": consultas,
            "total_events": total_events,
            "last_event_at": last_event_at.isoformat() if last_event_at else None,
        })

    cpfs_data.sort(key=lambda c: c["cpf"])

    return cpfs_data


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


async def get_db_identifications_with_expiry(session: AsyncSession) -> list[dict[str, Any]]:
    """
    Busca todos os registros com drive_file_id setado e situation=AD (APROVADO).
    Extrai identification + expiration_date do payload.
    
    Retorna: [
        {"identification": "ABC1234", "validity_date": "2026-10-20", "type": "placa"},
        {"identification": "251.967.558-61", "validity_date": "2026-10-20", "type": "cpf"},
    ]
    """
    stmt = (
        select(WebhookEvent)
        .where(WebhookEvent.drive_file_id.is_not(None))
    )
    result = await session.execute(stmt)
    events = result.scalars().all()
    
    identifications: list[dict[str, Any]] = []
    
    for event in events:
        payload = desanitize_payload(event.payload)
        
        identification = None
        validity_date = None
        id_type = None
        
        if event.webhook_type == "PESQUISACONCULTA":
            situation = payload.get("situation")
            if situation != "AD":
                continue
            
            identification = payload.get("identification")
            validity_date = payload.get("expiration_date")
            if payload.get("identification_type") in ("V", "C"):
                id_type = "placa"
            else:
                id_type = "cpf"
        elif event.webhook_type in ("CHECKLIST", "RESULTADOCHECKLIST"):
            identification = payload.get("codchecklist")
            validity_date = payload.get("dataexpiracao")
            id_type = "placa"
        
        if identification and validity_date:
            identifications.append({
                "identification": identification,
                "validity_date": validity_date,
                "type": id_type,
            })
    
    return identifications


async def get_all_approved_identifications(session: AsyncSession) -> list[dict[str, Any]]:
    """
    Busca TODOS os registros com situation=AD (APROVADO), independente de ter drive_file_id.
    Usado para comparar com arquivos do Drive e encontrar pendentes.
    
    Retorna: [
        {"id": 1, "identification": "ABC1234", "validity_date": "2026-10-20", "type": "placa", "base64": "..."},
    ]
    """
    stmt = (
        select(WebhookEvent)
        .where(WebhookEvent.webhook_type == "PESQUISACONCULTA")
    )
    result = await session.execute(stmt)
    events = result.scalars().all()
    
    identifications: list[dict[str, Any]] = []
    
    for event in events:
        payload = desanitize_payload(event.payload)
        
        situation = payload.get("situation")
        if situation != "AD":
            continue
        
        identification = payload.get("identification")
        validity_date = payload.get("expiration_date")
        base64_data = payload.get("base64")
        identification_type = payload.get("identification_type", "")
        
        if identification_type in ("V", "C"):
            id_type = "placa"
        else:
            id_type = "cpf"
        
        if identification and validity_date:
            identifications.append({
                "id": event.id,
                "identification": identification,
                "validity_date": validity_date,
                "type": id_type,
                "base64": base64_data,
                "drive_file_id": event.drive_file_id,
            })
    
    return identifications

async def update_drive_file(session: AsyncSession, event_id: int, drive_file_id: str, drive_file_url: str) -> bool:
    """
    Atualiza o registro com drive_file_id e drive_file_url após upload.
    """
    from sqlalchemy import update as sql_update
    
    stmt = (
        sql_update(WebhookEvent)
        .where(WebhookEvent.id == event_id)
        .values(drive_file_id=drive_file_id, drive_file_url=drive_file_url)
    )
    await session.execute(stmt)
    await session.commit()
    return True