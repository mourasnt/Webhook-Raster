import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from src.config import settings
from core.crypto import now_sp_str

logger = logging.getLogger(__name__)

AUDIT_LOG_FILE = Path(__file__).parent.parent / settings.AUDIT_LOG_FILE
AUDIT_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)


def log_audit_event(
    action: str,
    details: Dict[str, Any],
    source_ip: Optional[str] = None,
    event_id: Optional[str] = None,
) -> None:
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
        logger.error(f"Falha ao registrar audit event: {e}")