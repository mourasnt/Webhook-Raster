import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from audit.logger import log_audit_event
from core.crypto import now_sp, now_sp_str
from core.database import get_async_session, init_db, shutdown_db, startup_db
import core.database_models
from middleware.idempotency import IdempotencyMiddleware
from repositories.webhook import (
    list_all_cpfs,
    list_all_placas,
    list_dados_cpfs,
    list_dados_placas,
    search_by_cpf,
    search_by_placa,
)
from services.search import (
    list_cpfs,
    list_dados_cpfs,
    list_dados_placas,
    list_placas,
    search_by_cpf as search_by_cpf_service,
    search_by_placa as search_by_placa_service,
    get_missing_drive_identifications,
    upload_pending_documents,
    sync_cadastros
)
from services.kafka_producer import RasterEventProducer
from services.webhook_processor import (
    process_checklist,
    process_pesquisa_consulta,
    process_resultado_checklist,
)
from src.config import settings
from src.dependencies import shutdown_redis, startup_redis

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL, logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=settings.REDIS_RATE_LIMIT_URL,
    default_limits=[settings.RATE_LIMIT],
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await startup_redis()
    await startup_db()
    await init_db()
    await RasterEventProducer.start()

    yield

    await RasterEventProducer.stop()
    await shutdown_redis()
    await shutdown_db()
    logger.info("Lifecycle → shutdown concluído")


app = FastAPI(
    title="Webhook API - RasterIntegra",
    description=(
        "API para receber webhooks de Checklist, Resultado de Checklist "
        "e Pesquisa/Consulta — com proteção contra replay, idempotência, "
        "rate limiting."
    ),
    version="2.1.0",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
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


app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

app.add_middleware(IdempotencyMiddleware)
app.add_middleware(SlowAPIMiddleware)


@app.get("/health", tags=["Health"])
@limiter.limit(settings.RATE_LIMIT)
async def health_check(request: Request):
    return {
        "status": "ok",
        "message": "Servidor webhook está operacional",
        "server_time": now_sp_str(),
    }


@app.post("/webhook", tags=["Webhooks"])
@limiter.limit(settings.RATE_LIMIT)
async def receive_webhook(request: Request):
    try:
        payload = await request.json()

        if not payload or payload == {}:
            raise HTTPException(status_code=400, detail="Body obrigatório")

        webhook_type = payload.get("metodo") or payload.get("method")

        if not webhook_type:
            raise HTTPException(
                status_code=400,
                detail="Payload deve conter campo 'metodo' ou 'method'",
            )

        event_id = getattr(request.state, "event_id", None)

        received_at = now_sp_str()
        received_at_dt = now_sp()

        source_ip = request.client.host if request.client else None

        if webhook_type == "CHECKLIST":
            return await process_checklist(
                payload, event_id, received_at, received_at_dt, source_ip
            )

        elif webhook_type == "RESULTADOCHECKLIST":
            return await process_resultado_checklist(
                payload, event_id, received_at, received_at_dt, source_ip
            )

        elif webhook_type == "PESQUISACONCULTA":
            return await process_pesquisa_consulta(
                payload, event_id, received_at, received_at_dt, source_ip
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


@app.get("/search/placa/{placa}", tags=["Search"])
@limiter.limit(settings.RATE_LIMIT)
async def search_by_placa_endpoint(request: Request, placa: str):
    source_ip = request.client.host if request.client else None
    async with get_async_session() as session:
        results = await search_by_placa_service(session, placa)

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
        results = await search_by_cpf_service(session, cpf)

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
        placas = await list_placas(session)

    log_audit_event(
        action="LIST_PLACAS",
        details={"total": len(placas)},
        source_ip=source_ip,
    )
    return {"total": len(placas), "placas": placas}


@app.get("/placasdados", tags=["Search"])
@limiter.limit(settings.RATE_LIMIT)
async def list_placas_dados_endpoint(request: Request):
    source_ip = request.client.host if request.client else None
    async with get_async_session() as session:
        placas_dados = await list_dados_placas(session)

    log_audit_event(
        action="LIST_PLACAS_DADOS",
        details={"total": len(placas_dados)},
        source_ip=source_ip,
    )
    return {"placas": placas_dados}


@app.get("/cpfs", tags=["Search"])
@limiter.limit(settings.RATE_LIMIT)
async def list_cpfs_endpoint(request: Request):
    source_ip = request.client.host if request.client else None
    async with get_async_session() as session:
        cpfs = await list_cpfs(session)

    log_audit_event(
        action="LIST_CPFS",
        details={"total": len(cpfs)},
        source_ip=source_ip,
    )
    return {"total": len(cpfs), "cpfs": cpfs}


@app.get("/cpfsdados", tags=["Search"])
@limiter.limit(settings.RATE_LIMIT)
async def list_cpfs_dados_endpoint(request: Request):
    source_ip = request.client.host if request.client else None
    async with get_async_session() as session:
        cpfs_dados = await list_dados_cpfs(session)

    log_audit_event(
        action="LIST_CPFS_DADOS",
        details={"total": len(cpfs_dados)},
        source_ip=source_ip,
    )
    return {"cpfs": cpfs_dados}


@app.get("/audit/missing-drive-files", tags=["Audit"])
@limiter.limit(settings.RATE_LIMIT)
async def list_missing_drive_files_endpoint(request: Request):
    source_ip = request.client.host if request.client else None
    async with get_async_session() as session:
        result = await get_missing_drive_identifications(session)

    log_audit_event(
        action="LIST_MISSING_DRIVE_FILES",
        details=result,
        source_ip=source_ip,
    )
    return result


@app.post("/audit/upload-pending", tags=["Audit"])
@limiter.limit(settings.RATE_LIMIT)
async def upload_pending_documents_endpoint(request: Request):
    source_ip = request.client.host if request.client else None
    async with get_async_session() as session:
        result = await upload_pending_documents(session)

    log_audit_event(
        action="UPLOAD_PENDING_DOCUMENTS",
        details=result,
        source_ip=source_ip,
    )
    return result

@app.post("/audit/sync-cadastros", tags=["Audit"])
@limiter.limit(settings.RATE_LIMIT)
async def sync_cadastros_endpoint(request: Request):
    source_ip = request.client.host if request.client else None
    async with get_async_session() as session:
        result = await sync_cadastros(session)

    log_audit_event(
        action="SYNC_CADASTROS",
        details=result,
        source_ip=source_ip,
    )
    return result
