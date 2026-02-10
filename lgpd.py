"""
Módulo de proteção de dados pessoais para conformidade LGPD.

Artigos relevantes:
  - Art. 5º, I e II — Definição de dado pessoal e dado pessoal sensível
  - Art. 46  — Medidas de segurança técnicas (criptografia)
  - Art. 48  — Comunicação de incidentes

Campos sensíveis são CRIPTOGRAFADOS (Fernet/AES) antes da persistência.
Os dados podem ser recuperados com a ENCRYPTION_KEY quando necessário
para atualização de sistemas.

Fluxo:
  1. Webhook recebido → dados completos em memória para processamento
  2. Antes de salvar no log → campos sensíveis criptografados
  3. Quando necessário → descriptografar com a chave para uso nos sistemas
"""

import logging
from typing import Any, Dict

from cryptography.fernet import Fernet, InvalidToken

from config import settings

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────
# Inicializar cifrador Fernet (AES-128-CBC + HMAC-SHA256)
# ──────────────────────────────────────────────────────────────────
_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    """Retorna instância singleton do Fernet com a ENCRYPTION_KEY."""
    global _fernet
    if _fernet is None:
        key = settings.ENCRYPTION_KEY
        if not key:
            raise RuntimeError(
                "ENCRYPTION_KEY não configurada. "
                "Gere uma com: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
            )
        _fernet = Fernet(key.encode() if isinstance(key, str) else key)
    return _fernet


# ──────────────────────────────────────────────────────────────────
# Campos sensíveis (LGPD Art. 5º, I e II)
# ──────────────────────────────────────────────────────────────────
FIELDS_TO_ENCRYPT: set[str] = {
    "identification",  # CPF / CNPJ
    "password",        # Senha
    "base64",          # Documento / foto
    "placa",           # Placa de veículo (identificação indireta)
}


def encrypt_value(value: str) -> str:
    """
    Criptografa um valor com Fernet (AES-128-CBC + HMAC-SHA256).

    Retorna string base64 com prefixo 'ENC::' para identificação.
    """
    if not value:
        return value
    try:
        f = _get_fernet()
        encrypted = f.encrypt(value.encode("utf-8"))
        return f"ENC::{encrypted.decode('utf-8')}"
    except Exception as e:
        logger.error(f"Erro ao criptografar campo: {e}")
        return "[ENCRYPTION_ERROR]"


def decrypt_value(encrypted_value: str) -> str:
    """
    Descriptografa um valor criptografado com Fernet.

    Espera string com prefixo 'ENC::'.
    Retorna o valor original em texto claro.
    """
    if not encrypted_value or not encrypted_value.startswith("ENC::"):
        return encrypted_value
    try:
        f = _get_fernet()
        token = encrypted_value[5:]  # Remove prefixo 'ENC::'
        decrypted = f.decrypt(token.encode("utf-8"))
        return decrypted.decode("utf-8")
    except InvalidToken:
        logger.error("Chave de descriptografia inválida ou token corrompido")
        return "[DECRYPTION_ERROR]"
    except Exception as e:
        logger.error(f"Erro ao descriptografar: {e}")
        return "[DECRYPTION_ERROR]"


def sanitize_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Retorna uma CÓPIA do payload com dados pessoais CRIPTOGRAFADOS.

    - Campos em FIELDS_TO_ENCRYPT → criptografados com Fernet (prefixo 'ENC::')
    - Recursivo para dicts e listas aninhados
    - O payload original em memória NÃO é modificado

    Os dados podem ser recuperados com decrypt_value() + ENCRYPTION_KEY.
    """
    sanitized: Dict[str, Any] = {}

    for key, value in payload.items():
        if key in FIELDS_TO_ENCRYPT and isinstance(value, str) and value:
            sanitized[key] = encrypt_value(value)
            logger.debug(f"LGPD: campo '{key}' criptografado nos logs")

        elif isinstance(value, dict):
            sanitized[key] = sanitize_payload(value)

        elif isinstance(value, list):
            sanitized[key] = [
                sanitize_payload(item) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            sanitized[key] = value

    return sanitized


def desanitize_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Retorna uma CÓPIA do payload com dados pessoais DESCRIPTOGRAFADOS.

    Operação inversa de sanitize_payload().
    Requer a mesma ENCRYPTION_KEY usada na criptografia.
    """
    restored: Dict[str, Any] = {}

    for key, value in payload.items():
        if isinstance(value, str) and value.startswith("ENC::"):
            restored[key] = decrypt_value(value)

        elif isinstance(value, dict):
            restored[key] = desanitize_payload(value)

        elif isinstance(value, list):
            restored[key] = [
                desanitize_payload(item) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            restored[key] = value

    return restored
