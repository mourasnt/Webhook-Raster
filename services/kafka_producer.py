import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional
from aiokafka import AIOKafkaProducer

from src.config import settings

logger = logging.getLogger(__name__)


class RasterEventProducer:
    _producer: Optional[AIOKafkaProducer] = None

    @classmethod
    async def start(cls):
        if cls._producer is None:
            cls._producer = AIOKafkaProducer(
                bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
                client_id="webhook-raster",
            )
            await cls._producer.start()
            logger.info("Raster Kafka producer started")

    @classmethod
    async def stop(cls):
        if cls._producer:
            await cls._producer.stop()
            cls._producer = None
            logger.info("Raster Kafka producer stopped")

    @classmethod
    async def publicar(cls, event_type: str, data: dict):
        if cls._producer is None:
            logger.warning("Kafka producer not started, skipping event %s", event_type)
            return

        event = {
            "specversion": "1.0",
            "type": event_type,
            "source": "/webhook-raster",
            "id": str(uuid.uuid4()),
            "time": datetime.now(timezone.utc).isoformat(),
            "datacontenttype": "application/json",
            "data": data,
        }

        payload = json.dumps(event, default=str).encode("utf-8")
        try:
            await cls._producer.send_and_wait("raster", payload)
            logger.debug("Event published: %s -> raster", event_type)
        except Exception as e:
            logger.error("Failed to publish event %s: %s", event_type, str(e))

    @classmethod
    async def publicar_pesquisa_completed(cls, identification: str, identification_type: Optional[str], situation: Optional[str], expiration_date: Optional[str], base64_data: Optional[str] = None):
        tipo_map = {"V": "veiculo", "C": "reboque", "PJ": "proprietario"}
        tipo = tipo_map.get(identification_type) if identification_type else None
        if not tipo:
            digits = "".join(c for c in identification if c.isdigit())
            tipo = "motorista" if len(digits) == 11 else "proprietario"

        await cls.publicar(
            event_type="raster.pesquisa.completed",
            data={
                "tipo": tipo,
                "identificador": identification,
                "situacao": situation,
                "validade": expiration_date,
                "conteudo_base64": base64_data,
            },
        )

    @classmethod
    async def publicar_checklist_completed(cls, payload: dict):
        await cls.publicar(
            event_type="raster.checklist.completed",
            data={
                "placa": payload.get("placa"),
                "motorista_cpf": payload.get("motorista_cpf"),
                "codchecklist": payload.get("codchecklist"),
                "resultado": payload.get("resultado"),
                "data": payload.get("data"),
            },
        )

    @classmethod
    async def publicar_resultado_checklist(cls, payload: dict):
        await cls.publicar(
            event_type="raster.checklist.resultado",
            data={
                "placa": payload.get("placa"),
                "motorista_cpf": payload.get("motorista_cpf"),
                "codchecklist": payload.get("codchecklist"),
                "itens": payload.get("itens"),
            },
        )
