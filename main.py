from contextlib import asynccontextmanager
import asyncio
import logging
from typing import Dict, Any
from datetime import datetime

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from audit import log_audit_event
from config import settings
from db import get_async_session, init_db, shutdown_db, startup_db
import db_models
from db_repository import (
    list_all_cpfs,
    list_all_placas,
    save_webhook_event,
    search_by_cpf,
    search_by_placa,
)
from dependencies import startup_redis, shutdown_redis
from middleware import IdempotencyMiddleware
from models import (
    ChecklistWebhookRequest,
    ResultadoChecklistWebhookRequest,
    PesquisaConsultaWebhookRequest,
)
from retention import retention_background_task
from security import now_sp, now_sp_str
from utils import save_webhook_log

# ──────────────────────────────────────────────────────────────────
# Logging
# ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL, logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────
# Rate Limiter  (slowapi + Redis backend)
# ──────────────────────────────────────────────────────────────────
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=settings.REDIS_RATE_LIMIT_URL,
    default_limits=[settings.RATE_LIMIT],
)

# ──────────────────────────────────────────────────────────────────
# Lifespan  (startup / shutdown)
# ──────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gerencia ciclo de vida: conecta/desconecta Redis + retention task."""
    await startup_redis()
    await startup_db()
    await init_db()

    # Iniciar background task de expurgo (LGPD Art. 15/16)
    retention_task = asyncio.create_task(retention_background_task())
    logger.info("Lifecycle → startup concluído (retenção LGPD ativa)")

    yield

    # Cancelar task de retenção
    retention_task.cancel()
    try:
        await retention_task
    except asyncio.CancelledError:
        pass

    await shutdown_redis()
    await shutdown_db()
    logger.info("Lifecycle → shutdown concluído")

# ──────────────────────────────────────────────────────────────────
# Aplicação FastAPI
# ──────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Webhook API - RasterIntegra",
    description=(
        "API para receber webhooks de Checklist, Resultado de Checklist "
        "e Pesquisa/Consulta — com proteção contra replay, idempotência, "
        "rate limiting e conformidade LGPD."
    ),
    version="2.1.0",
    lifespan=lifespan,
)

# ──────────────────────────────────────────────────────────────────
# Rate Limit exceeded handler com audit trail (LGPD Art. 37)
# ──────────────────────────────────────────────────────────────────
async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    """Handler customizado para 429 com registro de auditoria."""
    source_ip = request.client.host if request.client else None
    log_audit_event(
        action="RATE_LIMITED",
        details={
            "path": str(request.url.path),
            "limit": str(exc.detail) if hasattr(exc, "detail") else "rate limit exceeded",
        },
        source_ip=source_ip,
    )
    return JSONResponse(
        status_code=429,
        content={"detail": "Rate limit excedido. Tente novamente em breve."},
    )


# Registrar rate limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

# Middlewares (ordem inversa de execução: último adicionado executa primeiro)
# 1) SlowAPI → avalia rate limit antes de tudo
# 2) Idempotency → rejeita duplicatas antes de chegar ao handler
app.add_middleware(IdempotencyMiddleware)
app.add_middleware(SlowAPIMiddleware)


# ──────────────────────────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────────────────────────
@app.get("/health", tags=["Health"])
@limiter.limit(settings.RATE_LIMIT)
async def health_check(request: Request):
    """Endpoint para verificar se o servidor está ativo."""
    return {
        "status": "ok",
        "message": "Servidor webhook está operacional",
        "server_time": now_sp_str(),
    }


@app.post("/webhook", tags=["Webhooks"])
@limiter.limit(settings.RATE_LIMIT)
async def receive_webhook(request: Request):
    """
    Recebe webhooks de três tipos:
    - CHECKLIST: Finalização de checklist
    - RESULTADOCHECKLIST: Resultado de checklist
    - PESQUISACONCULTA: Resultado de pesquisa e consulta

    Proteções ativas:
    - Idempotência via SHA256 do body (Redis, TTL 24 h)
    - Rate limiting global por IP (100 req/min padrão)
    - Validação de timestamp quando presente no payload
    - Criptografia de dados pessoais nos logs (LGPD)
    """
    try:
        body = await request.json()
        url = body.get("url", "")
        payload = body.get("payload", {})

        if not payload:
            raise HTTPException(status_code=400, detail="Campo 'payload' obrigatório")

        # Identificar tipo de webhook pelo campo metodo ou method
        webhook_type = payload.get("metodo") or payload.get("method")

        if not webhook_type:
            raise HTTPException(
                status_code=400,
                detail="Payload deve conter campo 'metodo' ou 'method'",
            )

        # Obter event_id do middleware (se disponível)
        event_id = getattr(request.state, "event_id", None)

        # Timestamp de recebimento (São Paulo)
        received_at = now_sp_str()
        received_at_dt = now_sp()

        # IP de origem para audit trail
        source_ip = request.client.host if request.client else None

        # Validar e processar conforme tipo
        if webhook_type == "CHECKLIST":
            return await process_checklist(
                body, url, payload, event_id, received_at, received_at_dt, source_ip
            )

        elif webhook_type == "RESULTADOCHECKLIST":
            return await process_resultado_checklist(
                body, url, payload, event_id, received_at, received_at_dt, source_ip
            )

        elif webhook_type == "PESQUISACONCULTA":
            return await process_pesquisa_consulta(
                body, url, payload, event_id, received_at, received_at_dt, source_ip
            )

        else:
            raise HTTPException(
                status_code=400,
                detail=f"Webhook type '{webhook_type}' não é suportado",
            )

    except HTTPException:
        raise

    except Exception as e:
        logger.error(f"Erro ao processar webhook: {e}")
        raise HTTPException(status_code=500, detail="Erro interno ao processar webhook")


# ──────────────────────────────────────────────────────────────────
# Processadores por tipo
# ──────────────────────────────────────────────────────────────────
async def process_checklist(
    body: Dict[str, Any],
    url: str,
    payload: Dict[str, Any],
    event_id: str | None,
    received_at: str,
    received_at_dt: datetime,
    source_ip: str | None,
):
    """Processa webhook CHECKLIST."""
    try:
        ChecklistWebhookRequest(**body)

        file_saved = save_webhook_log("CHECKLIST", payload, url, event_id, received_at)
        if not file_saved:
            logger.warning("Falha ao salvar log em arquivo para CHECKLIST")

        async with get_async_session() as session:
            await save_webhook_event(
                session,
                "CHECKLIST",
                url,
                payload,
                event_id,
                received_at_dt,
                source_ip,
            )

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
        raise HTTPException(status_code=422, detail=f"Dados inválidos: {e}")


async def process_resultado_checklist(
    body: Dict[str, Any],
    url: str,
    payload: Dict[str, Any],
    event_id: str | None,
    received_at: str,
    received_at_dt: datetime,
    source_ip: str | None,
):
    """Processa webhook RESULTADOCHECKLIST."""
    try:
        ResultadoChecklistWebhookRequest(**body)

        file_saved = save_webhook_log("RESULTADOCHECKLIST", payload, url, event_id, received_at)
        if not file_saved:
            logger.warning("Falha ao salvar log em arquivo para RESULTADOCHECKLIST")

        async with get_async_session() as session:
            await save_webhook_event(
                session,
                "RESULTADOCHECKLIST",
                url,
                payload,
                event_id,
                received_at_dt,
                source_ip,
            )

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
        raise HTTPException(status_code=422, detail=f"Dados inválidos: {e}")


async def process_pesquisa_consulta(
    body: Dict[str, Any],
    url: str,
    payload: Dict[str, Any],
    event_id: str | None,
    received_at: str,
    received_at_dt: datetime,
    source_ip: str | None,
):
    """Processa webhook PESQUISACONCULTA."""
    try:
        PesquisaConsultaWebhookRequest(**body)

        file_saved = save_webhook_log("PESQUISACONCULTA", payload, url, event_id, received_at)
        if not file_saved:
            logger.warning("Falha ao salvar log em arquivo para PESQUISACONCULTA")

        async with get_async_session() as session:
            await save_webhook_event(
                session,
                "PESQUISACONCULTA",
                url,
                payload,
                event_id,
                received_at_dt,
                source_ip,
            )

        logger.info(f"Pesquisa/Consulta recebida e salva: {payload.get('id')}")
        log_audit_event(
            action="WEBHOOK_RECEIVED",
            details={
                "webhook_type": "PESQUISACONCULTA",
                "id": payload.get("id"),
                "situation": payload.get("situation"),
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
            },
        )

    except ValueError as e:
        raise HTTPException(status_code=422, detail=f"Dados inválidos: {e}")


# ──────────────────────────────────────────────────────────────────
# Endpoints de pesquisa (Postgres)
# ──────────────────────────────────────────────────────────────────
@app.get("/search/placa/{placa}", tags=["Search"])
@limiter.limit(settings.RATE_LIMIT)
async def search_by_placa_endpoint(request: Request, placa: str):
    source_ip = request.client.host if request.client else None
    async with get_async_session() as session:
        results = await search_by_placa(session, placa)

    log_audit_event(
        action="SEARCH_PLACA",
        details={"placa": placa, "total": len(results)},
        source_ip=source_ip,
    )
    return {"placa": placa, "total": len(results), "results": results}


@app.get("/search/cpf/{cpf}", tags=["Search"])
@limiter.limit(settings.RATE_LIMIT)
async def search_by_cpf_endpoint(request: Request, cpf: str):
    source_ip = request.client.host if request.client else None
    async with get_async_session() as session:
        results = await search_by_cpf(session, cpf)

    log_audit_event(
        action="SEARCH_CPF",
        details={"cpf": cpf, "total": len(results)},
        source_ip=source_ip,
    )
    return {"cpf": cpf, "total": len(results), "results": results}


@app.get("/placas", tags=["Search"])
@limiter.limit(settings.RATE_LIMIT)
async def list_placas_endpoint(request: Request):
    source_ip = request.client.host if request.client else None
    async with get_async_session() as session:
        placas = await list_all_placas(session)

    log_audit_event(
        action="LIST_PLACAS",
        details={"total": len(placas)},
        source_ip=source_ip,
    )
    return {"total": len(placas), "placas": placas}


@app.get("/cpfs", tags=["Search"])
@limiter.limit(settings.RATE_LIMIT)
async def list_cpfs_endpoint(request: Request):
    source_ip = request.client.host if request.client else None
    async with get_async_session() as session:
        cpfs = await list_all_cpfs(session)

    log_audit_event(
        action="LIST_CPFS",
        details={"total": len(cpfs)},
        source_ip=source_ip,
    )
    return {"total": len(cpfs), "cpfs": cpfs}


# ──────────────────────────────────────────────────────────────────
# Entrypoint local (produção usa Docker → uvicorn direto)
# ──────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn

    print("""
    ╔════════════════════════════════════════════════════════════════╗
    ║  Webhook API - RasterIntegra v2.1 (LGPD + Segurança)        ║
    ║                                                                ║
    ║  Servidor rodando em: http://localhost:8000                   ║
    ║  Documentação:        http://localhost:8000/docs              ║
    ║                                                                ║
    ║  Segurança:                                                   ║
    ║  ✓ Idempotência via SHA256 + Redis (TTL 24h)                 ║
    ║  ✓ Rate Limiting global (100 req/min por IP)                 ║
    ║  ✓ Proteção contra Replay (timestamp validation)             ║
    ║                                                                ║
    ║  LGPD:                                                        ║
    ║  ✓ Criptografia Fernet de dados pessoais nos logs            ║
    ║  ✓ Expurgo automático (30 dias)                              ║
    ║  ✓ Audit trail (logs/audit.json)                             ║
    ║                                                                ║
    ║  Endpoints:                                                   ║
    ║  ✓ POST /webhook       - Receber webhooks                    ║
    ║  ✓ GET  /health        - Health check                        ║
    ╚════════════════════════════════════════════════════════════════╝
    """)

    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
