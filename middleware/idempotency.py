import logging

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from audit.logger import log_audit_event
from core.crypto import check_idempotency, generate_event_id, validate_timestamp
from src.dependencies import get_redis

logger = logging.getLogger(__name__)


class IdempotencyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method != "POST" or request.url.path != "/webhook":
            return await call_next(request)

        try:
            body = await request.body()

            if not body:
                return JSONResponse(
                    status_code=400,
                    content={"detail": "Request body vazio"},
                )

            event_id = generate_event_id(body)

            try:
                import json
                payload_data = json.loads(body)
                payload = payload_data.get("payload", {})
                timestamp_str = payload.get("timestamp")

                if not validate_timestamp(timestamp_str):
                    source_ip = request.client.host if request.client else None
                    log_audit_event(
                        action="TIMESTAMP_REJECTED",
                        details={"timestamp": timestamp_str},
                        source_ip=source_ip,
                        event_id=event_id,
                    )
                    return JSONResponse(
                        status_code=400,
                        content={
                            "detail": "Timestamp do evento fora da janela permitida (>5min)",
                            "event_id": event_id,
                        },
                    )
            except (json.JSONDecodeError, AttributeError):
                pass

            redis = get_redis()
            is_new = await check_idempotency(redis, event_id)

            if not is_new:
                source_ip = request.client.host if request.client else None
                logger.warning(f"Requisição duplicada rejeitada: event_id={event_id[:16]}...")
                log_audit_event(
                    action="DUPLICATE_REJECTED",
                    details={"reason": "Evento já processado (idempotência)"},
                    source_ip=source_ip,
                    event_id=event_id,
                )
                return JSONResponse(
                    status_code=409,
                    content={
                        "detail": "Evento já processado",
                        "event_id": event_id,
                    },
                    headers={"X-Event-Id": event_id},
                )

            request.state.event_id = event_id
            request.state._body = body.decode('utf-8') if body else None

            response = await call_next(request)

            response.headers["X-Event-Id"] = event_id

            return response

        except RuntimeError as e:
            if "Redis" in str(e):
                logger.error(f"Redis indisponível no middleware: {e}")
                logger.warning("Redis indisponível — bypass de idempotência (fail-open)")
                log_audit_event(
                    action="REDIS_FAIL_OPEN",
                    details={"error": str(e)},
                    source_ip=request.client.host if request.client else None,
                )
                response = await call_next(request)
                return response
            raise

        except Exception as e:
            logger.error(f"Erro no middleware de idempotência: {e}")
            return JSONResponse(
                status_code=500,
                content={"detail": "Erro interno na verificação de idempotência"},
            )