"""
Módulo para integração com Google Drive API.
Faz upload de documentos em base64 para uma pasta específica no Drive.
"""

import base64
import io
import json
import logging
from datetime import datetime
from typing import Tuple, Optional

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from googleapiclient.errors import HttpError

from config import settings

logger = logging.getLogger(__name__)

# Singleton para o serviço do Drive
_drive_service = None


def _extract_http_error_reason(error: HttpError) -> str:
    """
    Extrai o motivo principal de um HttpError da API Google.

    Retorna string vazia caso não consiga inferir o motivo.
    """
    try:
        if hasattr(error, "content") and error.content:
            content = error.content.decode("utf-8") if isinstance(error.content, bytes) else str(error.content)
            payload = json.loads(content)
            details = payload.get("error", {}).get("errors", [])
            if details and isinstance(details, list):
                reason = details[0].get("reason")
                if reason:
                    return reason
    except Exception:
        pass

    message = str(error)
    if "storageQuotaExceeded" in message:
        return "storageQuotaExceeded"
    return ""


def _load_service_account_credentials() -> service_account.Credentials:
    """
    Carrega e valida credenciais de service account do Google.

    Também normaliza private_key com "\\n" literal para quebras de linha reais,
    evitando falhas de assinatura JWT quando o JSON foi serializado incorretamente.
    """
    with open(settings.GOOGLE_CREDENTIALS_FILE, "r", encoding="utf-8") as credentials_file:
        service_account_info = json.load(credentials_file)

    required_fields = ["type", "private_key", "client_email", "token_uri"]
    missing_fields = [field for field in required_fields if not service_account_info.get(field)]
    if missing_fields:
        raise ValueError(
            f"credentials.json inválido. Campos ausentes: {', '.join(missing_fields)}"
        )

    if service_account_info.get("type") != "service_account":
        raise ValueError("credentials.json inválido. O campo 'type' deve ser 'service_account'.")

    private_key = service_account_info.get("private_key", "")
    if "\\n" in private_key and "\n" not in private_key:
        service_account_info["private_key"] = private_key.replace("\\n", "\n")

    return service_account.Credentials.from_service_account_info(
        service_account_info,
        scopes=['https://www.googleapis.com/auth/drive.file']
    )


def _get_drive_service():
    """
    Retorna uma instância singleton do serviço Google Drive.
    
    Returns:
        Resource: Serviço Google Drive API v3
        
    Raises:
        FileNotFoundError: Se credentials.json não for encontrado
        Exception: Se houver erro na autenticação
    """
    global _drive_service
    
    if _drive_service is None:
        try:
            credentials = _load_service_account_credentials()
            _drive_service = build('drive', 'v3', credentials=credentials)
            logger.info("Serviço Google Drive inicializado com sucesso")
        except FileNotFoundError:
            logger.error(f"Arquivo de credenciais não encontrado: {settings.GOOGLE_CREDENTIALS_FILE}")
            raise
        except ValueError as e:
            logger.error(f"Credenciais Google Drive inválidas: {e}")
            raise
        except Exception as e:
            logger.error(f"Erro ao inicializar serviço Google Drive: {e}")
            raise
    
    return _drive_service


def _detect_mime_type(base64_string: str) -> str:
    """
    Detecta o tipo MIME do arquivo a partir do base64.
    
    Args:
        base64_string: String em base64 (pode incluir data URI)
        
    Returns:
        str: Tipo MIME detectado (jpg, png, pdf, etc.)
    """
    # Remove data URI se presente
    if "," in base64_string:
        header, base64_string = base64_string.split(",", 1)
        # Extrai MIME do header se presente
        if "data:" in header and "/" in header:
            mime = header.split("data:")[1].split(";")[0]
            return mime
    
    # Decodifica início do arquivo para verificar magic bytes
    try:
        decoded = base64.b64decode(base64_string[:100])
        
        # Magic bytes para tipos comuns
        if decoded.startswith(b'\xff\xd8\xff'):
            return "image/jpeg"
        elif decoded.startswith(b'\x89PNG'):
            return "image/png"
        elif decoded.startswith(b'%PDF'):
            return "application/pdf"
        elif decoded.startswith(b'GIF89a') or decoded.startswith(b'GIF87a'):
            return "image/gif"
        elif decoded.startswith(b'\x42\x4d'):
            return "image/bmp"
        
    except Exception as e:
        logger.warning(f"Erro ao detectar MIME type: {e}")
    
    # Default para JPEG se não conseguir detectar
    return "image/jpeg"


def format_filename(identification: str, expiration_date: str) -> str:
    """
    Formata o nome do arquivo conforme especificação:
    "identificação - VALIDADE (DD-MM-YYYY).extensão"
    
    Args:
        identification: CPF, CNPJ ou outro identificador
        expiration_date: Data de validade no formato ISO (YYYY-MM-DD)
        
    Returns:
        str: Nome do arquivo formatado (sem extensão)
        
    Examples:
        >>> format_filename("12345678900", "2025-06-01")
        "12345678900 - VALIDADE (01-06-2025)"
    """
    try:
        # Converte data de YYYY-MM-DD para DD-MM-YYYY
        date_obj = datetime.strptime(expiration_date, "%Y-%m-%d")
        formatted_date = date_obj.strftime("%d-%m-%Y")
    except ValueError:
        # Se já estiver em outro formato, tenta DD/MM/YYYY
        try:
            date_obj = datetime.strptime(expiration_date, "%d/%m/%Y")
            formatted_date = date_obj.strftime("%d-%m-%Y")
        except ValueError:
            # Usa a data original se não conseguir parsear
            formatted_date = expiration_date.replace("/", "-")
    
    return f"{identification} - VALIDADE ({formatted_date})"


def upload_document(
    base64_data: str,
    identification: str,
    expiration_date: str,
    folder_id: Optional[str] = None
) -> Optional[Tuple[str, str]]:
    """
    Faz upload de documento em base64 para o Google Drive.
    
    Args:
        base64_data: String em base64 do documento
        identification: CPF/CNPJ para nome do arquivo
        expiration_date: Data de validade (YYYY-MM-DD ou DD/MM/YYYY)
        folder_id: ID da pasta no Drive (usa settings.GOOGLE_DRIVE_FOLDER_ID se None)
        
    Returns:
        tuple[str, str] | None: (file_id, file_url) se sucesso, None se falhar
        
    Example:
        >>> result = upload_document("iVBORw0KGgo...", "12345678900", "2025-06-01")
        >>> if result:
        >>>     file_id, file_url = result
        >>>     print(f"Upload: {file_url}")
    """
    try:
        service = _get_drive_service()
        
        # Remove prefixo data URI se presente
        if "," in base64_data:
            _, base64_data = base64_data.split(",", 1)
        
        # Decodifica base64
        file_bytes = base64.b64decode(base64_data)
        
        # Detecta tipo MIME e extensão
        mime_type = _detect_mime_type(base64_data)
        extension_map = {
            "image/jpeg": "jpg",
            "image/png": "png",
            "application/pdf": "pdf",
            "image/gif": "gif",
            "image/bmp": "bmp",
        }
        extension = extension_map.get(mime_type, "jpg")
        
        # Formata nome do arquivo
        filename_base = format_filename(identification, expiration_date)
        filename = f"{filename_base}.{extension}"
        
        # Prepara upload
        file_stream = io.BytesIO(file_bytes)
        media = MediaIoBaseUpload(file_stream, mimetype=mime_type, resumable=True)
        
        # Metadados do arquivo
        file_metadata = {
            'name': filename,
            'mimeType': mime_type
        }
        
        # Define pasta de destino
        target_folder_id = folder_id or settings.GOOGLE_DRIVE_FOLDER_ID
        if target_folder_id:
            file_metadata['parents'] = [target_folder_id]
        
        # Faz upload
        logger.info(f"Iniciando upload: {filename} ({len(file_bytes)} bytes)")
        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, webViewLink, webContentLink',
            supportsAllDrives=True
        ).execute()
        
        file_id = file.get('id')
        file_url = file.get('webViewLink') or file.get('webContentLink')
        
        logger.info(f"Upload concluído: {filename} - ID: {file_id}")
        
        return (file_id, file_url)
        
    except HttpError as e:
        reason = _extract_http_error_reason(e)
        if reason == "storageQuotaExceeded":
            logger.error(
                "Upload bloqueado por quota do Drive (storageQuotaExceeded). "
                "Para Service Account, use pasta em Shared Drive e garanta permissão de membro "
                "(ex: Content Manager). folder_id=%s",
                target_folder_id,
            )
        logger.error(f"Erro HTTP ao fazer upload para Google Drive: {e}")
        return None
    except Exception as e:
        logger.error(f"Erro inesperado ao fazer upload para Google Drive: {e}")
        return None


def delete_document(file_id: str) -> bool:
    """
    Remove um documento do Google Drive.
    
    Args:
        file_id: ID do arquivo no Google Drive
        
    Returns:
        bool: True se deletado com sucesso, False caso contrário
    """
    try:
        service = _get_drive_service()
        service.files().delete(fileId=file_id, supportsAllDrives=True).execute()
        logger.info(f"Arquivo deletado do Drive: {file_id}")
        return True
    except HttpError as e:
        logger.error(f"Erro ao deletar arquivo do Drive {file_id}: {e}")
        return False
    except Exception as e:
        logger.error(f"Erro inesperado ao deletar arquivo do Drive {file_id}: {e}")
        return False


def get_file_info(file_id: str) -> Optional[dict]:
    """
    Obtém informações sobre um arquivo no Google Drive.
    
    Args:
        file_id: ID do arquivo no Google Drive
        
    Returns:
        dict | None: Informações do arquivo ou None se não encontrado
    """
    try:
        service = _get_drive_service()
        file = service.files().get(
            fileId=file_id,
            fields='id, name, mimeType, size, createdTime, modifiedTime, webViewLink',
            supportsAllDrives=True
        ).execute()
        return file
    except HttpError as e:
        logger.error(f"Erro ao obter informações do arquivo {file_id}: {e}")
        return None
    except Exception as e:
        logger.error(f"Erro inesperado ao obter informações do arquivo {file_id}: {e}")
        return None
