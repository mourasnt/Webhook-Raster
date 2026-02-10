from contextlib import asynccontextmanager
import logging
from typing import Dict, Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from config import settings
from dependencies import startup_redis, shutdown_redis
from middleware import IdempotencyMiddleware
from models import (
    ChecklistWebhookRequest,
    ResultadoChecklistWebhookRequest,
    PesquisaConsultaWebhookRequest,
)
from security import now_sp_str
from utils import save_webhook_log, get_webhook_logs

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
    """Gerencia ciclo de vida: conecta/desconecta Redis."""
    await startup_redis()
    logger.info("Lifecycle → startup concluído")
    yield
    await shutdown_redis()
    logger.info("Lifecycle → shutdown concluído")

# ──────────────────────────────────────────────────────────────────
# Aplicação FastAPI
# ──────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Webhook API - RasterIntegra",
    description=(
        "API para receber webhooks de Checklist, Resultado de Checklist "
        "e Pesquisa/Consulta — com proteção contra replay, idempotência "
        "e rate limiting."
    ),
    version="2.0.0",
    lifespan=lifespan,
)

# Registrar rate limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

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

        # Validar e processar conforme tipo
        if webhook_type == "CHECKLIST":
            return await process_checklist(body, url, payload, event_id, received_at)

        elif webhook_type == "RESULTADOCHECKLIST":
            return await process_resultado_checklist(body, url, payload, event_id, received_at)

        elif webhook_type == "PESQUISACONCULTA":
            return await process_pesquisa_consulta(body, url, payload, event_id, received_at)

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
):
    """Processa webhook CHECKLIST."""
    try:
        ChecklistWebhookRequest(**body)

        success = save_webhook_log("CHECKLIST", payload, url, event_id, received_at)

        if success:
            logger.info(f"Checklist recebido e salvo: {payload.get('codchecklist')}")
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
        raise Exception("Erro ao salvar log em arquivo")

    except ValueError as e:
        raise HTTPException(status_code=422, detail=f"Dados inválidos: {e}")


async def process_resultado_checklist(
    body: Dict[str, Any],
    url: str,
    payload: Dict[str, Any],
    event_id: str | None,
    received_at: str,
):
    """Processa webhook RESULTADOCHECKLIST."""
    try:
        ResultadoChecklistWebhookRequest(**body)

        success = save_webhook_log("RESULTADOCHECKLIST", payload, url, event_id, received_at)

        if success:
            logger.info(f"Resultado Checklist recebido e salvo: {payload.get('codchecklist')}")
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
        raise Exception("Erro ao salvar log em arquivo")

    except ValueError as e:
        raise HTTPException(status_code=422, detail=f"Dados inválidos: {e}")


async def process_pesquisa_consulta(
    body: Dict[str, Any],
    url: str,
    payload: Dict[str, Any],
    event_id: str | None,
    received_at: str,
):
    """Processa webhook PESQUISACONCULTA."""
    try:
        PesquisaConsultaWebhookRequest(**body)

        success = save_webhook_log("PESQUISACONCULTA", payload, url, event_id, received_at)

        if success:
            logger.info(f"Pesquisa/Consulta recebida e salva: {payload.get('id')}")
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
        raise Exception("Erro ao salvar log em arquivo")

    except ValueError as e:
        raise HTTPException(status_code=422, detail=f"Dados inválidos: {e}")


# ──────────────────────────────────────────────────────────────────
# Endpoints auxiliares
# ──────────────────────────────────────────────────────────────────
@app.get("/logs/{webhook_type}", tags=["Logs"])
@limiter.limit(settings.RATE_LIMIT)
async def get_logs(request: Request, webhook_type: str):
    """Retorna todos os logs de um tipo de webhook específico."""
    if webhook_type not in ("CHECKLIST", "RESULTADOCHECKLIST", "PESQUISACONCULTA"):
        raise HTTPException(
            status_code=400,
            detail="Webhook type inválido. Use: CHECKLIST, RESULTADOCHECKLIST ou PESQUISACONCULTA",
        )

    logs = get_webhook_logs(webhook_type)
    return {
        "webhook_type": webhook_type,
        "total_records": len(logs),
        "logs": logs,
    }


# ──────────────────────────────────────────────────────────────────
# Entrypoint local (produção usa Docker → uvicorn direto)
# ──────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn

    print("""
    ╔════════════════════════════════════════════════════════════════╗
    ║        Webhook API - RasterIntegra v2.0 (Segurança)          ║
    ║                                                                ║
    ║  Servidor rodando em: http://localhost:8000                   ║
    ║  Documentação:        http://localhost:8000/docs              ║
    ║                                                                ║
    ║  Segurança ativa:                                             ║
    ║  ✓ Idempotência via SHA256 + Redis (TTL 24h)                 ║
    ║  ✓ Rate Limiting global (100 req/min por IP)                 ║
    ║  ✓ Proteção contra Replay (timestamp validation)             ║
    ║                                                                ║
    ║  Endpoints:                                                   ║
    ║  ✓ POST /webhook       - Receber webhooks                    ║
    ║  ✓ GET  /health        - Health check                        ║
    ║  ✓ GET  /logs/{type}   - Visualizar logs salvos              ║
    ╚════════════════════════════════════════════════════════════════╝
    """)

    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
