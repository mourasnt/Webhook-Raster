import logging

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from dependencies import get_redis
from security import generate_event_id, check_idempotency, validate_timestamp

logger = logging.getLogger(__name__)


class IdempotencyMiddleware(BaseHTTPMiddleware):
    """
    Middleware de proteção contra replay e idempotência.

    Intercepta apenas POST /webhook:
    1. Lê bytes brutos do body → gera event_id (SHA256)
    2. Consulta Redis para verificar duplicidade (SET NX atômico)
    3. Se duplicado → 409 Conflict
    4. Se novo → passa adiante e adiciona X-Event-Id na response

    Também valida timestamp do payload se presente.
    """

    async def dispatch(self, request: Request, call_next):
        # Aplicar apenas em POST /webhook
        if request.method != "POST" or request.url.path != "/webhook":
            return await call_next(request)

        try:
            # Ler body bytes brutos
            body = await request.body()

            if not body:
                return JSONResponse(
                    status_code=400,
                    content={"detail": "Request body vazio"},
                )

            # Gerar event_id via SHA256
            event_id = generate_event_id(body)

            # Verificar timestamp do payload (se presente)
            try:
                import json
                payload_data = json.loads(body)
                payload = payload_data.get("payload", {})
                timestamp_str = payload.get("timestamp")

                if not validate_timestamp(timestamp_str):
                    return JSONResponse(
                        status_code=400,
                        content={
                            "detail": "Timestamp do evento fora da janela permitida (>5min)",
                            "event_id": event_id,
                        },
                    )
            except (json.JSONDecodeError, AttributeError):
                # Se não for JSON válido, deixar o handler tratar o erro
                pass

            # Verificar idempotência no Redis
            redis = get_redis()
            is_new = await check_idempotency(redis, event_id)

            if not is_new:
                logger.warning(f"Requisição duplicada rejeitada: event_id={event_id[:16]}...")
                return JSONResponse(
                    status_code=409,
                    content={
                        "detail": "Evento já processado",
                        "event_id": event_id,
                    },
                    headers={"X-Event-Id": event_id},
                )

            # Injetar event_id no state do request para uso downstream
            request.state.event_id = event_id

            # Processar request normalmente
            response = await call_next(request)

            # Adicionar header X-Event-Id na response
            response.headers["X-Event-Id"] = event_id

            return response

        except RuntimeError as e:
            if "Redis" in str(e):
                logger.error(f"Redis indisponível no middleware: {e}")
                # Em caso de falha do Redis, permitir o request (fail-open)
                # para não derrubar o serviço por indisponibilidade do cache
                logger.warning("Redis indisponível — bypass de idempotência (fail-open)")
                response = await call_next(request)
                return response
            raise

        except Exception as e:
            logger.error(f"Erro no middleware de idempotência: {e}")
            return JSONResponse(
                status_code=500,
                content={"detail": "Erro interno na verificação de idempotência"},
            )
