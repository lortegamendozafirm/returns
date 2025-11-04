# src/clients/drive_client.py
from __future__ import annotations

import re
from io import BytesIO
from typing import Optional

from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload

from src.auth import build_drive_client, build_docs_client
from src.utils.logger import get_logger

logger = get_logger(__name__)

DOC_MIME = "application/vnd.google-apps.document"
SHEET_MIME = "application/vnd.google-apps.spreadsheet"

def find_file_in_folder_by_name(
    folder_id: str,
    name: str,
    mime_type: str,
    *,
    page_size: int = 10,
) -> Optional[dict]:
    """Busca por nombre y tipo dentro de una carpeta (incluye Shared Drives)."""
    drive = build_drive_client()
    q = (
        f"'{folder_id}' in parents and trashed=false "
        f"and mimeType='{mime_type}' and name='{name}'"
    )
    resp = drive.files().list(
        q=q,
        fields="files(id,name,mimeType,modifiedTime,owners)",
        pageSize=page_size,
        supportsAllDrives=True,
        includeItemsFromAllDrives=True,
    ).execute()
    files = resp.get("files", [])
    return files[0] if files else None

def assert_sa_has_access(file_id: str, *, use_docs_api: bool = True) -> None:
    """
    Verifica que la Service Account actual pueda acceder al archivo.
    - Por defecto usa Docs API (mejor para Google Docs) porque con 'drive.file'
      Drive puede ocultar 403 como 404 por privacidad.
    - Si el archivo no es un Google Doc (p. ej. PDF binario), usa use_docs_api=False para forzar Drive API.
    Lanza HttpError si no hay acceso.
    """
    if use_docs_api:
        docs = build_docs_client()
        try:
            docs.documents().get(documentId=file_id).execute()
            return
        except HttpError as e:
            logger.error(f"[Docs Access] SA no puede acceder a {file_id}: {e}")
            raise

    drive = build_drive_client()
    try:
        drive.files().get(
            fileId=file_id,
            fields="id,name,mimeType,owners,permissions",
            supportsAllDrives=True,
        ).execute()
    except HttpError as e:
        logger.error(f"[Drive Access] SA no puede acceder a {file_id}: {e}")
        raise

def grant_editor_to_sa(file_id: str, sa_email: str) -> None:
    """
    Otorga rol de editor a la SA sobre un archivo específico (si el caller tiene permisos).
    No envía notificación por email.
    """
    drive = build_drive_client()
    body = {"type": "user", "role": "writer", "emailAddress": sa_email}
    drive.permissions().create(
        fileId=file_id,
        body=body,
        sendNotificationEmail=False,
        supportsAllDrives=True,
    ).execute()
    logger.info(f"🔐 Se otorgó 'writer' a {sa_email} sobre {file_id}.")

# ------- Utilidades para PDFs/Drive --------

def parse_drive_url_to_id(url: str) -> str | None:
    """
    Extrae fileId de URLs tipo:
    https://drive.google.com/file/d/<FILE_ID>/view?...
    """
    m = re.search(r"/file/d/([a-zA-Z0-9_-]+)/", url)
    return m.group(1) if m else None

def download_file_bytes(file_id: str) -> bytes:
    """
    Descarga un archivo (binario) de Drive por fileId (útil para PDFs).
    """
    drive = build_drive_client()
    request = drive.files().get_media(fileId=file_id, supportsAllDrives=True)
    fh = BytesIO()
    downloader = MediaIoBaseDownload(fd=fh, request=request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return fh.getvalue()
