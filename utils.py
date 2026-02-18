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

# Arquivo de logs de erros (todos os erros HTTP 4xx e 5xx)
ERROR_LOG_FILE = LOGS_DIR / "errors.json"


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


def save_error_log(
    status_code: int,
    error_detail: str,
    payload: Optional[Dict[str, Any]] = None,
    source_ip: Optional[str] = None,
    event_id: Optional[str] = None,
    request_method: Optional[str] = None,
    request_url: Optional[str] = None,
    traceback: Optional[str] = None,
    webhook_type: Optional[str] = None,
) -> bool:
    """
    Salva log de erro HTTP em arquivo JSON dedicado.
    
    Registra TODOS os erros 4xx e 5xx com payload completo e contexto.
    Ideal para debugging de erros 400, 422, 500.
    
    Args:
        status_code: Código HTTP (400, 422, 500, etc.)
        error_detail: Mensagem de erro
        payload: Payload completo recebido (será sanitizado)
        source_ip: IP de origem da requisição
        event_id: ID único do evento (SHA256 do body)
        request_method: Método HTTP (POST, GET, etc.)
        request_url: URL da requisição
        traceback: Stack trace completo (para erros 500)
        webhook_type: Tipo do webhook se identificado
    
    Returns:
        bool: True se salvo com sucesso, False caso contrário
        
    Example:
        >>> save_error_log(
        ...     status_code=422,
        ...     error_detail="Dados inválidos: campo 'placa' obrigatório",
        ...     payload={"metodo": "CHECKLIST", "codchecklist": 123},
        ...     source_ip="192.168.1.1",
        ...     webhook_type="CHECKLIST"
        ... )
    """
    try:
        from datetime import datetime
        
        # Sanitizar payload se presente
        safe_payload = None
        if payload:
            try:
                safe_payload = sanitize_payload(payload)
            except Exception:
                # Se falhar sanitização, salva sem sanitizar (melhor ter dados que nada)
                safe_payload = payload
        
        # Timestamp atual
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        error_entry = {
            "timestamp": now,
            "status_code": status_code,
            "error_type": "CLIENT_ERROR" if 400 <= status_code < 500 else "SERVER_ERROR",
            "error_detail": error_detail,
            "webhook_type": webhook_type,
            "event_id": event_id,
            "request": {
                "method": request_method,
                "url": request_url,
                "source_ip": source_ip,
            },
            "payload": safe_payload,
            "traceback": traceback,
        }
        
        # Append ao arquivo (JSON Lines format)
        with open(ERROR_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(error_entry, ensure_ascii=False, indent=None) + "\n")
        
        logger.info(f"Erro {status_code} registrado em error log: {error_detail[:100]}")
        return True
        
    except Exception as e:
        logger.error(f"FALHA ao salvar error log: {e}")
        return False


def get_error_logs(limit: Optional[int] = None) -> list:
    """
    Retorna logs de erros salvos.
    
    Args:
        limit: Número máximo de logs a retornar (None = todos)
    
    Returns:
        list: Lista de dicts com os error logs (mais recentes primeiro)
    """
    try:
        if not ERROR_LOG_FILE.exists():
            return []
        
        logs = []
        with open(ERROR_LOG_FILE, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    logs.append(json.loads(line))
        
        # Retorna mais recentes primeiro
        logs.reverse()
        
        if limit:
            return logs[:limit]
        return logs
        
    except Exception as e:
        logger.error(f"Erro ao ler error logs: {e}")
        return []
