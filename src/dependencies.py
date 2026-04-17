import logging
from redis.asyncio import Redis, ConnectionPool

from src.config import settings

logger = logging.getLogger(__name__)

_redis_pool: ConnectionPool | None = None
_redis_client: Redis | None = None


async def startup_redis() -> Redis:
    global _redis_pool, _redis_client

    _redis_pool = ConnectionPool.from_url(
        settings.REDIS_URL,
        decode_responses=True,
        max_connections=20,
    )
    _redis_client = Redis(connection_pool=_redis_pool)

    try:
        await _redis_client.ping()
        logger.info("Conexão Redis estabelecida com sucesso")
    except Exception as e:
        logger.error(f"Falha ao conectar no Redis: {e}")
        raise

    return _redis_client


async def shutdown_redis() -> None:
    global _redis_pool, _redis_client

    if _redis_client:
        await _redis_client.aclose()
        logger.info("Conexão Redis encerrada")
    if _redis_pool:
        await _redis_pool.disconnect()

    _redis_client = None
    _redis_pool = None


def get_redis() -> Redis:
    if _redis_client is None:
        raise RuntimeError("Redis não inicializado. Verifique o lifecycle da aplicação.")
    return _redis_client