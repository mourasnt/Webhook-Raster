import logging
from typing import Optional

import requests

from src.config import settings

logger = logging.getLogger(__name__)


async def send_whatsapp_message(text: str, phone: Optional[str] = None) -> bool:
    """
    Envia mensagem via Evolution API.

    Args:
        text: Texto da mensagem
        phone: Número de destino (usa config se não informado)

    Returns:
        bool: True se enviado com sucesso
    """
    if not settings.WHATSAPP_ENABLED:
        logger.info("WhatsApp desabilitado, mensagem ignorada")
        return True

    if not phone:
        phone = settings.WHATSAPP_DESTINATION

    try:
        url = f"{settings.WHATSAPP_API_URL}/message/sendText/{settings.WHATSAPP_INSTANCE}"

        payload = {
            "number": phone,
            "text": text
        }

        headers = {
            "Content-Type": "application/json",
            "apikey": settings.WHATSAPP_API_KEY
        }

        response = requests.post(url, json=payload, headers=headers, timeout=10)

        if response.status_code in (200, 201):
            logger.info(f"Mensagem WhatsApp enviada para {phone}")
            return True
        else:
            logger.error(f"Erro ao enviar WhatsApp: {response.status_code} - {response.text}")
            return False

    except Exception as e:
        logger.error(f"Erro ao enviar WhatsApp: {e}")
        return False