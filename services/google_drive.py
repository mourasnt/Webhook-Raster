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

from src.config import settings

logger = logging.getLogger(__name__)

_drive_service = None


def _extract_http_error_reason(error: HttpError) -> str:
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
    if "," in base64_string:
        header, base64_string = base64_string.split(",", 1)
        if "data:" in header and "/" in header:
            mime = header.split("data:")[1].split(";")[0]
            return mime

    try:
        decoded = base64.b64decode(base64_string[:100])

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

    return "image/jpeg"


def format_filename(identification: str, expiration_date: str) -> str:
    try:
        date_obj = datetime.strptime(expiration_date, "%Y-%m-%d")
        formatted_date = date_obj.strftime("%d-%m-%Y")
    except ValueError:
        try:
            date_obj = datetime.strptime(expiration_date, "%d/%m/%Y")
            formatted_date = date_obj.strftime("%d-%m-%Y")
        except ValueError:
            formatted_date = expiration_date.replace("/", "-")

    return f"{identification} - VALIDADE ({formatted_date})"


def upload_document(
    base64_data: str,
    identification: str,
    expiration_date: str,
    folder_id: Optional[str] = None
) -> Optional[Tuple[str, str]]:
    try:
        service = _get_drive_service()

        if "," in base64_data:
            _, base64_data = base64_data.split(",", 1)

        file_bytes = base64.b64decode(base64_data)

        mime_type = _detect_mime_type(base64_data)
        extension_map = {
            "image/jpeg": "jpg",
            "image/png": "png",
            "application/pdf": "pdf",
            "image/gif": "gif",
            "image/bmp": "bmp",
        }
        extension = extension_map.get(mime_type, "jpg")

        filename_base = format_filename(identification, expiration_date)
        filename = f"{filename_base}.{extension}"

        file_stream = io.BytesIO(file_bytes)
        media = MediaIoBaseUpload(file_stream, mimetype=mime_type, resumable=True)

        file_metadata = {
            'name': filename,
            'mimeType': mime_type
        }

        target_folder_id = folder_id or settings.GOOGLE_DRIVE_FOLDER_ID
        if target_folder_id:
            file_metadata['parents'] = [target_folder_id]

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
                " Para Service Account, use pasta em Shared Drive e garanta permissão. folder_id=%s",
                target_folder_id,
            )
        logger.error(f"Erro HTTP ao fazer upload para Google Drive: {e}")
        return None
    except Exception as e:
        logger.error(f"Erro inesperado ao fazer upload para Google Drive: {e}")
        return None


def delete_document(file_id: str) -> bool:
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