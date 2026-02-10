import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from lgpd import sanitize_payload

# Definir caminho para logs
LOGS_DIR = Path(__file__).parent / "logs"
LOGS_DIR.mkdir(exist_ok=True)

logger = logging.getLogger(__name__)

LOG_FILES = {
    "CHECKLIST": LOGS_DIR / "checklist.json",
    "RESULTADOCHECKLIST": LOGS_DIR / "resultadochecklist.json",
    "PESQUISACONCULTA": LOGS_DIR / "pesquisaconculta.json",
}


def save_webhook_log(
    webhook_type: str,
    payload: Dict[str, Any],
    url: str,
    event_id: Optional[str] = None,
    received_at: Optional[str] = None,
) -> bool:
    """
    Salva o webhook recebido em arquivo JSON específico.

    Args:
        webhook_type: Tipo do webhook (CHECKLIST, RESULTADOCHECKLIST, PESQUISACONCULTA)
        payload: Dict com os dados do payload
        url: URL original do webhook
        event_id: SHA256 do body para rastreabilidade (gerado pelo middleware)
        received_at: Timestamp de recebimento no timezone de São Paulo

    Returns:
        bool: True se salvo com sucesso, False caso contrário
    """
    try:
        log_file = LOG_FILES.get(webhook_type)
        if not log_file:
            return False

        # LGPD: sanitizar dados pessoais antes de persistir
        safe_payload = sanitize_payload(payload)

        log_entry = {
            "received_at": received_at,
            "event_id": event_id,
            "webhook_type": webhook_type,
            "url": url,
            "payload": safe_payload,
        }

        # Append ao arquivo (JSON Lines format — um objeto JSON por linha)
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

        return True
    except Exception as e:
        logger.error(f"Erro ao salvar log: {e}")
        return False


def get_webhook_logs(webhook_type: str) -> list:
    """
    Retorna todos os logs de um tipo de webhook específico.
    
    Args:
        webhook_type: Tipo do webhook (CHECKLIST, RESULTADOCHECKLIST, PESQUISACONCULTA)
    
    Returns:
        list: Lista de dicts com os logs
    """
    try:
        log_file = LOG_FILES.get(webhook_type)
        if not log_file or not log_file.exists():
            return []
        
        logs = []
        with open(log_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    logs.append(json.loads(line))
        return logs
    except Exception as e:
        print(f"Erro ao ler logs: {e}")
        return []
