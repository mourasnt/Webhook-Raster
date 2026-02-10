"""
Audit trail para conformidade LGPD Art. 37 (relatório de impacto).

Registra todas as operações relevantes sobre dados pessoais em arquivo
dedicado (JSON Lines) separado dos logs de webhook.

Eventos registrados:
  - WEBHOOK_RECEIVED    — webhook processado com sucesso
  - DUPLICATE_REJECTED  — requisição duplicada rejeitada (idempotência)
  - TIMESTAMP_REJECTED  — timestamp fora da janela permitida
  - RATE_LIMITED        — requisição bloqueada por rate limiting
  - RETENTION_PURGE     — registros expirados removidos (expurgo)
  - REDIS_FAIL_OPEN     — Redis indisponível, bypass de segurança
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from config import settings
from security import now_sp_str

logger = logging.getLogger(__name__)

AUDIT_LOG_FILE = Path(__file__).parent / settings.AUDIT_LOG_FILE
AUDIT_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)


def log_audit_event(
    action: str,
    details: Dict[str, Any],
    source_ip: Optional[str] = None,
    event_id: Optional[str] = None,
) -> None:
    """
    Registra um evento de auditoria no arquivo dedicado.

    Args:
        action: Tipo do evento (ex: WEBHOOK_RECEIVED, DUPLICATE_REJECTED)
        details: Dict com contexto do evento
        source_ip: Endereço IP do requisitante (quando aplicável)
        event_id: SHA256 do body (quando aplicável)
    """
    try:
        entry = {
            "timestamp": now_sp_str(),
            "action": action,
            "source_ip": source_ip,
            "event_id": event_id,
            "details": details,
        }

        with open(AUDIT_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    except Exception as e:
        # Audit nunca deve derrubar a aplicação
        logger.error(f"Falha ao registrar audit event: {e}")
