import logging
from redis.asyncio import Redis, ConnectionPool
from config import settings

logger = logging.getLogger(__name__)

# Pool de conexão singleton
_redis_pool: ConnectionPool | None = None
_redis_client: Redis | None = None


async def startup_redis() -> Redis:
    """Inicializa pool de conexão Redis no startup da aplicação."""
    global _redis_pool, _redis_client

    _redis_pool = ConnectionPool.from_url(
        settings.REDIS_URL,
        decode_responses=True,
        max_connections=20,
    )
    _redis_client = Redis(connection_pool=_redis_pool)

    # Verificar conectividade
    try:
        await _redis_client.ping()
        logger.info("Conexão Redis estabelecida com sucesso")
    except Exception as e:
        logger.error(f"Falha ao conectar no Redis: {e}")
        raise

    return _redis_client


async def shutdown_redis() -> None:
    """Fecha conexão Redis no shutdown da aplicação."""
    global _redis_pool, _redis_client

    if _redis_client:
        await _redis_client.aclose()
        logger.info("Conexão Redis encerrada")
    if _redis_pool:
        await _redis_pool.disconnect()

    _redis_client = None
    _redis_pool = None


def get_redis() -> Redis:
    """Retorna o cliente Redis ativo. Usar como dependency do FastAPI."""
    if _redis_client is None:
        raise RuntimeError("Redis não inicializado. Verifique o lifecycle da aplicação.")
    return _redis_client
