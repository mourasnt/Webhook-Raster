from datetime import datetime
import logging
from typing import Optional

import httpx

from src.config import settings

logger = logging.getLogger(__name__)

_LOGIN_ENDPOINT = "/auth/login"
_RESULTADO_ENDPOINT = "/resultados-pesquisa"


def _mapear_tipo_entidade(identification_type: Optional[str], identification: str) -> str:
    if identification_type == "V":
        return "veiculo"
    if identification_type == "C":
        return "reboque"
    if identification_type == "PJ":
        return "proprietario"

    digits = "".join(c for c in identification if c.isdigit())
    if identification_type in ("PF", "P") or identification_type is None:
        if len(digits) == 11:
            return "motorista"
        if len(digits) == 14:
            return "proprietario"

    logger.warning(
        "Tipo de entidade não mapeado: identification_type=%s, identification=%s. Usando 'motorista' como fallback",
        identification_type, identification,
    )
    return "motorista"


def _converter_data_br(data_str: Optional[str]) -> Optional[str]:
    if not data_str:
        return None
    data_str = data_str.strip()
    if "/" in data_str:
        return data_str
    try:
        return datetime.strptime(data_str, "%Y-%m-%d").strftime("%d/%m/%Y")
    except ValueError:
        logger.warning("Formato de data não reconhecido: %s. Enviando como está.", data_str)
        return data_str


async def _obter_token() -> Optional[str]:
    base_url = settings.CADASTRO_API_URL.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{base_url}{_LOGIN_ENDPOINT}",
                json={
                    "username": settings.CADASTRO_USERNAME,
                    "password": settings.CADASTRO_PASSWORD,
                },
            )
            if resp.is_success:
                data = resp.json()
                token = data.get("access_token")
                if token:
                    logger.info("Autenticado no Cadastro API com sucesso")
                    return token
                logger.error("Resposta do login não contém access_token: %s", data)
            else:
                logger.error("Falha no login do Cadastro API: %s - %s", resp.status_code, resp.text)
    except Exception as e:
        logger.error("Erro ao autenticar no Cadastro API: %s", e)
    return None


async def buscar_nome_motorista(cpf: str) -> Optional[str]:
    token = await _obter_token()
    if not token:
        return None

    cpf_digits = "".join(c for c in cpf if c.isdigit())
    base_url = settings.CADASTRO_API_URL.rstrip("/")
    headers = {"Authorization": f"Bearer {token}"}

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{base_url}/motoristas",
                params={"$filter": f"cpf eq '{cpf_digits}'", "$top": 1, "$count": "true"},
                headers=headers,
            )
            if resp.is_success:
                data = resp.json()
                items = data.get("value", [])
                if items:
                    nome = items[0].get("nome")
                    if nome:
                        logger.info("Nome encontrado para CPF %s: %s", cpf_digits, nome)
                        return nome
                logger.info("Motorista não encontrado no Cadastro para CPF %s", cpf_digits)
            else:
                logger.warning(
                    "Cadastro API retornou %s ao buscar motorista: %s",
                    resp.status_code, resp.text[:200],
                )
    except Exception as e:
        logger.error("Erro ao buscar nome do motorista no Cadastro API: %s", e)
    return None


async def notify_cadastro(
    identification: str,
    identification_type: Optional[str],
    situation: Optional[str],
    expiration_date: Optional[str],
    base64_data: Optional[str] = None,
) -> None:
    if not settings.CADASTRO_PASSWORD:
        logger.info("CADASTRO_PASSWORD não configurada. Pulando notificação do Cadastro API.")
        return

    token = await _obter_token()
    if not token:
        return

    tipo = _mapear_tipo_entidade(identification_type, identification)
    base_url = settings.CADASTRO_API_URL.rstrip("/")

    payload = {
        "tipo": tipo,
        "identificador": identification,
        "resultado": situation or "",
        "validade": _converter_data_br(expiration_date),
        "conteudo_base64": base64_data,
        "nome_arquivo": f"{identification} - resultado.pdf",
        "tipo_arquivo": "application/pdf",
    }

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{base_url}{_RESULTADO_ENDPOINT}",
                json=payload,
                headers=headers,
            )
            if resp.is_success:
                logger.info(
                    "Resultado de pesquisa enviado ao Cadastro API: tipo=%s, identificador=%s, situacao=%s",
                    tipo, identification, situation,
                )
            else:
                logger.warning(
                    "Cadastro API retornou %s: %s",
                    resp.status_code, resp.text[:500],
                )
    except Exception as e:
        logger.error("Erro ao notificar Cadastro API: %s", e)
