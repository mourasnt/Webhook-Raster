import logging
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base

from config import settings

logger = logging.getLogger(__name__)

Base = declarative_base()

_engine = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _require_engine():
    if _engine is None or _session_factory is None:
        raise RuntimeError("Banco de dados não inicializado. Verifique o lifecycle da aplicação.")


async def startup_db() -> None:
    """Inicializa engine e session factory do Postgres."""
    global _engine, _session_factory
    _engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    _session_factory = async_sessionmaker(bind=_engine, expire_on_commit=False, class_=AsyncSession)
    logger.info("Conexão com Postgres configurada")


async def init_db() -> None:
    """Cria tabelas caso não existam."""
    _require_engine()
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Migração automática concluída (create_all)")


async def shutdown_db() -> None:
    """Encerra engine do Postgres."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        logger.info("Conexão Postgres encerrada")
    _engine = None
    _session_factory = None


@asynccontextmanager
async def get_async_session():
    """Cria uma sessão async para operações no banco."""
    _require_engine()
    async with _session_factory() as session:
        yield session
