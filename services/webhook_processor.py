import logging
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi.responses import JSONResponse

from audit.logger import log_audit_event
from core.crypto import now_sp, now_sp_str, sanitize_payload
from core.database import get_async_session
from repositories.webhook import save_webhook_event
from schemas.webhook import ChecklistPayload, PesquisaConsultaPayload, ResultadoChecklistPayload
from services.cadastro_integration import buscar_nome_motorista, notify_cadastro
from services.google_drive import upload_document
from services.kafka_producer import RasterEventProducer
from services.whatsapp import send_whatsapp_message
from src.config import settings

logger = logging.getLogger(__name__)


async def process_checklist(
    payload: Dict[str, Any],
    event_id: Optional[str],
    received_at: str,
    received_at_dt: datetime,
    source_ip: Optional[str],
) -> JSONResponse:
    try:
        ChecklistPayload(**payload)

        async with get_async_session() as session:
            await save_webhook_event(
                session,
                "CHECKLIST",
                payload,
                event_id,
                received_at_dt,
                source_ip,
            )

        await RasterEventProducer.publicar_checklist_completed(payload)

        logger.info(f"Checklist recebido e salvo: {payload.get('codchecklist')}")
        log_audit_event(
            action="WEBHOOK_RECEIVED",
            details={"webhook_type": "CHECKLIST", "codchecklist": payload.get("codchecklist")},
            source_ip=source_ip,
            event_id=event_id,
        )
        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "message": "Webhook CHECKLIST recebido e salvo com sucesso",
                "webhook_type": "CHECKLIST",
                "codchecklist": payload.get("codchecklist"),
                "event_id": event_id,
                "received_at": received_at,
            },
        )

    except ValueError as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail=f"Dados inválidos: {e}")


async def process_resultado_checklist(
    payload: Dict[str, Any],
    event_id: Optional[str],
    received_at: str,
    received_at_dt: datetime,
    source_ip: Optional[str],
) -> JSONResponse:
    try:
        ResultadoChecklistPayload(**payload)

        async with get_async_session() as session:
            await save_webhook_event(
                session,
                "RESULTADOCHECKLIST",
                payload,
                event_id,
                received_at_dt,
                source_ip,
            )

        await RasterEventProducer.publicar_resultado_checklist(payload)

        logger.info(f"Resultado Checklist recebido e salvo: {payload.get('codchecklist')}")
        log_audit_event(
            action="WEBHOOK_RECEIVED",
            details={
                "webhook_type": "RESULTADOCHECKLIST",
                "codchecklist": payload.get("codchecklist"),
                "resultado": payload.get("resultado"),
            },
            source_ip=source_ip,
            event_id=event_id,
        )
        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "message": "Webhook RESULTADOCHECKLIST recebido e salvo com sucesso",
                "webhook_type": "RESULTADOCHECKLIST",
                "codchecklist": payload.get("codchecklist"),
                "resultado": payload.get("resultado"),
                "event_id": event_id,
                "received_at": received_at,
            },
        )

    except ValueError as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail=f"Dados inválidos: {e}")


async def process_pesquisa_consulta(
    payload: Dict[str, Any],
    event_id: Optional[str],
    received_at: str,
    received_at_dt: datetime,
    source_ip: Optional[str],
) -> JSONResponse:
    try:
        PesquisaConsultaPayload(**payload)

        drive_file_id = None
        drive_file_url = None

        if payload.get("base64"):
            try:
                identification = payload.get("identification")
                expiration_date = payload.get("expiration_date")

                if identification and expiration_date:
                    result = upload_document(
                        base64_data=payload["base64"],
                        identification=identification,
                        expiration_date=expiration_date
                    )

                    if result:
                        drive_file_id, drive_file_url = result
                        logger.info(f"Documento enviado para Google Drive: {drive_file_id}")

            except Exception as e:
                logger.error(f"Erro ao fazer upload para Google Drive: {e}")

        async with get_async_session() as session:
            await save_webhook_event(
                session,
                "PESQUISACONCULTA",
                payload,
                event_id,
                received_at_dt,
                source_ip,
                drive_file_id,
                drive_file_url,
            )

        logger.info(f"Pesquisa/Consulta recebida e salva: {payload.get('id')}")

        if settings.WHATSAPP_ENABLED:
            identification_type = payload.get("identification_type", "")
            identification = payload.get("identification", "")
            status = payload.get("situation", "")

            is_vehicle = identification_type != "P"
            nome_motorista = None

            if not is_vehicle:
                nome_motorista = await buscar_nome_motorista(identification)

            if is_vehicle:
                titulo = "*RETORNO DE PESQUISA*"
                mensagem = f"*PLACA:* {identification}"
            else:
                titulo = "*RETORNO DE PESQUISA*"
                mensagem = f"*CPF:* {identification[:3]}.{identification[3:6]}.{identification[6:9]}-{identification[9:]}"
                if nome_motorista:
                    mensagem = f"*NOME:* {nome_motorista}\n{mensagem}"

            if status == "AD":
                resultado = "\n\n✅*APROVADO*✅"
            else:
                resultado = "\n\n❌*INCONCLUSIVO*❌"

            message = f"{titulo}\n\n{mensagem}{resultado}"
            await send_whatsapp_message(message)

        await RasterEventProducer.publicar_pesquisa_completed(
            identification=payload.get("identification", ""),
            identification_type=payload.get("identification_type"),
            situation=payload.get("situation"),
            expiration_date=payload.get("expiration_date"),
            base64_data=payload.get("base64"),
        )

        try:
            await notify_cadastro(
                identification=payload.get("identification", ""),
                identification_type=payload.get("identification_type"),
                situation=payload.get("situation"),
                expiration_date=payload.get("expiration_date"),
                base64_data=payload.get("base64"),
            )
        except Exception as e:
            logger.warning("Falha ao notificar Cadastro API (fluxo continua): %s", e)

        log_audit_event(
            action="WEBHOOK_RECEIVED",
            details={
                "webhook_type": "PESQUISACONCULTA",
                "id": payload.get("id"),
                "situation": payload.get("situation"),
                "drive_uploaded": drive_file_id is not None,
            },
            source_ip=source_ip,
            event_id=event_id,
        )
        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "message": "Webhook PESQUISACONCULTA recebido e salvo com sucesso",
                "webhook_type": "PESQUISACONCULTA",
                "id": payload.get("id"),
                "situation": payload.get("situation"),
                "event_id": event_id,
                "received_at": received_at,
                "drive_file_id": drive_file_id,
                "drive_file_url": drive_file_url,
            },
        )

    except ValueError as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail=f"Dados inválidos: {e}")