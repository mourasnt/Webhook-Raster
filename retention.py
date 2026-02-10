"""
Módulo de retenção e expurgo automático de logs (LGPD Art. 15 e 16).

Remove automaticamente registros mais antigos que LOG_RETENTION_DAYS.
Executa no startup e a cada 24h em background task.
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

from audit import log_audit_event
from config import settings
from db import get_async_session
from db_models import WebhookEvent
from utils import LOG_FILES
from sqlalchemy import delete

logger = logging.getLogger(__name__)

SP_TZ = ZoneInfo(settings.TIMEZONE)


def purge_old_entries(log_file: Path, max_age_days: int) -> int:
    """
    Remove entradas mais antigas que max_age_days de um arquivo JSON Lines.

    Args:
        log_file: Caminho do arquivo de log
        max_age_days: Idade máxima em dias

    Returns:
        Número de entradas removidas
    """
    if not log_file.exists():
        return 0

    cutoff = datetime.now(SP_TZ) - timedelta(days=max_age_days)
    kept: list[str] = []
    removed = 0

    try:
        with open(log_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                try:
                    entry = json.loads(line)
                    # Tentar parsear o campo de timestamp (received_at ou timestamp)
                    ts_str = entry.get("received_at") or entry.get("timestamp")
                    if ts_str:
                        entry_time = _parse_timestamp(ts_str)
                        if entry_time and entry_time < cutoff:
                            removed += 1
                            continue

                    kept.append(line)

                except json.JSONDecodeError:
                    # Linha inválida — remover
                    removed += 1

        # Reescrever arquivo apenas com entradas válidas
        with open(log_file, "w", encoding="utf-8") as f:
            for line in kept:
                f.write(line + "\n")

    except Exception as e:
        logger.error(f"Erro no expurgo de {log_file.name}: {e}")

    return removed


def _parse_timestamp(ts_str: str) -> Optional[datetime]:
    """Tenta parsear timestamp em múltiplos formatos."""
    formats = [
        "%Y-%m-%d %H:%M:%S %Z",   # 2026-02-10 14:30:00 -03
        "%Y-%m-%d %H:%M:%S",       # 2026-02-10 14:30:00
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(ts_str, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=SP_TZ)
            return dt
        except ValueError:
            continue

    # Tentar ISO 8601
    try:
        dt = datetime.fromisoformat(ts_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=SP_TZ)
        return dt
    except (ValueError, TypeError):
        return None


async def purge_old_db_entries() -> int:
    """Remove registros antigos do Postgres conforme LOG_RETENTION_DAYS."""
    cutoff = datetime.now(SP_TZ) - timedelta(days=settings.LOG_RETENTION_DAYS)
    async with get_async_session() as session:
        stmt = delete(WebhookEvent).where(WebhookEvent.received_at < cutoff)
        result = await session.execute(stmt)
        await session.commit()
        removed = result.rowcount if result.rowcount is not None else 0
        return removed


async def run_retention_cleanup() -> dict[str, int]:
    """
    Executa expurgo em todos os arquivos de log e no Postgres.

    Returns:
        Dict com {tipo_webhook: registros_removidos}
    """
    results: dict[str, int] = {}

    for webhook_type, log_file in LOG_FILES.items():
        removed = purge_old_entries(log_file, settings.LOG_RETENTION_DAYS)
        results[webhook_type] = removed
        if removed > 0:
            logger.info(f"Retenção: {removed} registros removidos de {webhook_type}")

    # Expurgar também o audit log
    audit_file = Path(__file__).parent / settings.AUDIT_LOG_FILE
    audit_removed = purge_old_entries(audit_file, settings.LOG_RETENTION_DAYS)
    results["AUDIT"] = audit_removed

    # Expurgo no banco
    db_removed = await purge_old_db_entries()
    results["DB"] = db_removed

    # Registrar no audit trail
    total = sum(results.values())
    log_audit_event(
        action="RETENTION_PURGE",
        details={
            "retention_days": settings.LOG_RETENTION_DAYS,
            "removed_by_type": results,
            "total_removed": total,
        },
    )

    if total > 0:
        logger.info(f"Retenção LGPD concluída: {total} registros removidos no total")
    else:
        logger.info("Retenção LGPD: nenhum registro expirado encontrado")

    return results


async def retention_background_task() -> None:
    """
    Background task que executa expurgo a cada 24h.
    Primeira execução imediata no startup.
    """
    while True:
        try:
            await run_retention_cleanup()
        except Exception as e:
            logger.error(f"Erro na task de retenção: {e}")

        # Aguardar 24h para próximo ciclo
        await asyncio.sleep(86400)
