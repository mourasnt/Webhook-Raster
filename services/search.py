import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from repositories import webhook as repo
from services import google_drive

from services.kafka_producer import RasterEventProducer

logger = logging.getLogger(__name__)


async def search_by_cpf(session: AsyncSession, cpf: str) -> list[dict[str, Any]]:
    logger.info(f"Buscando por CPF: {cpf}")
    return await repo.search_by_cpf(session, cpf)


async def search_by_placa(session: AsyncSession, placa: str) -> list[dict[str, Any]]:
    logger.info(f"Buscando por placa: {placa}")
    return await repo.search_by_placa(session, placa)


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


async def get_db_identifications_with_expiry(session: AsyncSession) -> list[dict[str, Any]]:
    logger.info("Buscando identificações com expiry do DB")
    return await repo.get_db_identifications_with_expiry(session)


async def get_missing_drive_identifications(session: AsyncSession) -> dict[str, int]:
    """
    Compara TODOS os registros approved (situation=AD) vs arquivos do Drive.
    Retorna contagem de CPFs e Placas que estão no DB mas não no Drive.
    """
    logger.info("Comparando identificações DB vs Drive")
    
    db_identifications = await repo.get_all_approved_identifications(session)
    
    db_set = set()
    for item in db_identifications:
        db_set.add((item["identification"], item["validity_date"]))
    
    logger.info(f"Identificações APROVADAS no DB: {len(db_set)}")
    
    drive_identifications = google_drive.list_drive_identifications()
    
    logger.info(f"Identificações no Drive: {len(drive_identifications)}")
    
    missing = db_set - drive_identifications
    
    missing_placas = 0
    missing_cpfs = 0
    
    for ident, date in missing:
        for item in db_identifications:
            if item["identification"] == ident and item["validity_date"] == date:
                if item["type"] == "placa":
                    missing_placas += 1
                else:
                    missing_cpfs += 1
                break
    
    logger.info(f"Faltando no Drive - Placas: {missing_placas}, CPFs: {missing_cpfs}")
    
    return {
        "quantidade_placas": missing_placas,
        "quantidade_cpfs": missing_cpfs,
    }


async def upload_pending_documents(session: AsyncSession) -> dict[str, Any]:
    """
    Faz upload dos documentos que estão no DB (situation=AD) mas não estão no Drive.
    """
    logger.info("Buscando registros pendentes de upload")
    
    db_identifications = await repo.get_all_approved_identifications(session)
    
    drive_identifications = google_drive.list_drive_identifications()
    
    logger.info(f"Total approved no DB: {len(db_identifications)}")
    logger.info(f"Total no Drive: {len(drive_identifications)}")
    
    uploaded_placas = 0
    uploaded_cpfs = 0
    failed = 0
    
    for record in db_identifications:
        key = (record["identification"], record["validity_date"])
        
        if key in drive_identifications:
            continue
        
        if not record.get("base64"):
            logger.warning(f"Sem base64: {record['identification']}")
            continue
        
        try:
            result = google_drive.upload_document(
                base64_data=record["base64"],
                identification=record["identification"],
                expiration_date=record["validity_date"]
            )
            
            if result:
                drive_file_id, drive_file_url = result
                await repo.update_drive_file(
                    session,
                    record["id"],
                    drive_file_id,
                    drive_file_url
                )
                logger.info(f"Upload realizado: {record['identification']}")
                
                if record["type"] == "placa":
                    uploaded_placas += 1
                else:
                    uploaded_cpfs += 1
            else:
                logger.warning(f"Upload falhou: {record['identification']}")
                failed += 1
                
        except Exception as e:
            logger.error(f"Erro ao fazer upload {record['identification']}: {e}")
            failed += 1
    
    logger.info(f"Upload concluído - Placas: {uploaded_placas}, CPFs: {uploaded_cpfs}, Falhos: {failed}")
    
    return {
        "quantidade_placas": uploaded_placas,
        "quantidade_cpfs": uploaded_cpfs,
        "falhos": failed,
    }


async def sync_cadastros(session: AsyncSession) -> dict[str, Any]:
    """
    Publica evento de todas as pesquisas aprovadas
    """
    db_identifications = await repo.get_all_approved_identifications(session)
    logger.info(f"Total approved no DB: {len(db_identifications)}")

    published = 0
    failed = 0

    for record in db_identifications:
        if not record.get("base64"):
            logger.warning(f"Sem base64: {record['identification']}")
            continue

        raster_type = record.get("identification_type") or None

        try:
            await RasterEventProducer.publicar_pesquisa_completed(
                identification=record["identification"],
                identification_type=raster_type,
                situation="AD",
                expiration_date=record["validity_date"],
                base64_data=record["base64"],
            )
            published += 1
        except Exception as e:
            logger.error(f"Erro ao publicar evento {record['identification']}: {e}")
            failed += 1

    return {
        "total": len(db_identifications),
        "publicados": published,
        "falhos": failed,
    }