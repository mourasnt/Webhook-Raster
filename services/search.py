import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from repositories import webhook as repo

logger = logging.getLogger(__name__)


async def search_by_placa(session: AsyncSession, placa: str) -> list[dict[str, Any]]:
    logger.info(f"Buscando por placa: {placa}")
    return await repo.search_by_placa(session, placa)


async def search_by_cpf(session: AsyncSession, cpf: str) -> list[dict[str, Any]]:
    logger.info(f"Buscando por CPF: {cpf}")
    return await repo.search_by_cpf(session, cpf)


async def list_placas(session: AsyncSession) -> list[str]:
    logger.info("Listando todas as placas")
    return await repo.list_all_placas(session)


async def list_cpfs(session: AsyncSession) -> list[str]:
    logger.info("Listando todos os CPFs")
    return await repo.list_all_cpfs(session)


async def list_dados_placas(session: AsyncSession) -> list[dict[str, Any]]:
    logger.info("Listando dados por placas")
    return await repo.list_dados_placas(session)


async def list_dados_cpfs(session: AsyncSession) -> list[dict[str, Any]]:
    logger.info("Listando dados por CPFs")
    return await repo.list_dados_cpfs(session)


async def purge_old_entries(session: AsyncSession) -> int:
    logger.info("Executando expurgo de registros antigos")
    return await repo.purge_old_db_entries(session)