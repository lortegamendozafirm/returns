# src/clients/gdocs_client.py
from __future__ import annotations

import time
import random
import socket
import ssl
import json

from typing import Any, Dict, List, Optional, TypedDict, cast, Iterator
from http.client import IncompleteRead

from googleapiclient.errors import HttpError
from googleapiclient.http import HttpRequest
from src.auth import build_docs_client
from src.utils.logger import get_logger

logger = get_logger(__name__)

# ========= Tipos (Google Docs API) =========

class StructuralElement(TypedDict, total=False):
    startIndex: int
    endIndex: int
    # Los siguientes campos pueden o no estar:
    paragraph: Dict[str, Any]
    table: Dict[str, Any]
    sectionBreak: Dict[str, Any]
    tableOfContents: Dict[str, Any]

class Body(TypedDict, total=False):
    content: List[StructuralElement]

class Document(TypedDict, total=False):
    title: str
    body: Body


def _extract_reason(err: HttpError) -> str:
    try:
        data = err.error_details or err.content or b""
        if isinstance(data, bytes):
            data = data.decode("utf-8", errors="ignore")
        j = json.loads(data)
        return j.get("error", {}).get("errors", [{}])[0].get("reason", "") or \
               j.get("error", {}).get("status", "")
    except Exception:
        return ""

# ========= Reintentos genéricos =========

_RETRY_STATUSES = {408, 429, 500, 502, 503, 504}

def _is_ssl_eof(e: BaseException) -> bool:
    msg = str(e).lower()
    return "eof occurred in violation of protocol" in msg or "tlsv" in msg

def _execute_with_retries(request: HttpRequest, *, max_retries: int = 6) -> Optional[Dict[str, Any]]:
    delay = 1.0
    for attempt in range(1, max_retries + 1):
        try:
            return cast(Dict[str, Any], request.execute(num_retries=0))
        except (IncompleteRead, ConnectionResetError, BrokenPipeError,
                ssl.SSLError, socket.timeout, OSError) as e:
            # Errores de transporte (incluye TLS/EOF)
            if attempt == max_retries:
                raise
            sleep = delay + random.uniform(0, delay * 0.5)
            kind = "SSL/EOF" if isinstance(e, ssl.SSLError) or _is_ssl_eof(e) else "RED"
            logger.warning(f"🔁 Retry {attempt}/{max_retries} por {kind}: {e}. Esperando {sleep:.1f}s…")
            time.sleep(sleep)
            delay = min(delay * 2, 20)
            # ⚠️ Para intentos altos, re-crea el cliente (por si la sesión quedó “sucia”)
            if attempt >= 3:
                from src.auth import build_docs_client
                _ = build_docs_client.cache_clear()  # limpia cache lru si usas Python 3.9+, si no, ignóralo
                build_docs_client()  # reconstruye cliente
            continue
        except HttpError as e:
            status = getattr(e, "status_code", None) or getattr(e.resp, "status", None)
            if status in _RETRY_STATUSES and attempt < max_retries:
                sleep = delay + random.uniform(0, delay * 0.5)
                logger.warning(f"🔁 Retry {attempt}/{max_retries} por HttpError {status}: {e}. Esperando {sleep:.1f}s…")
                time.sleep(sleep)
                delay = min(delay * 2, 20)
                continue
            raise

# --- LECTURA DE CONTENIDO (tipado + reintentos) ---

def _iter_text(doc: Document) -> Iterator[str]:
    """Itera sobre los `textRun.content` de todos los párrafos."""
    body = cast(Body, doc.get("body", {}))
    for elem in cast(List[StructuralElement], body.get("content", [])):
        para = elem.get("paragraph")
        if not para:
            continue
        for el in para.get("elements", []):
            text_run = el.get("textRun")
            if not text_run:
                continue
            content = text_run.get("content") or ""
            if content:
                yield content

def get_document_content(document_id: str) -> str:
    """
    Devuelve el texto plano del Google Doc `document_id`.
    Hace `documents.get` y concatena todos los `textRun.content`.
    """
    docs = build_docs_client()
    get_req: HttpRequest = docs.documents().get(documentId=document_id)
    doc_raw: Optional[Dict[str, Any]] = _execute_with_retries(get_req)
    doc: Document = cast(Document, doc_raw)
    # Concatena conservando saltos de línea que vienen en los textRuns
    return "".join(_iter_text(doc))

# ========= Helpers tipados =========

def _get_end_index(doc: Document) -> int:
    """
    Devuelve el endIndex del último StructuralElement del documento.
    Maneja casos donde body/content no existe.
    """
    body = cast(Body, doc.get("body", {}))
    content = cast(List[StructuralElement], body.get("content", []))
    if not content:
        # Si no hay contenido, por seguridad devolvemos 1 (inicio del doc)
        return 1
    last = content[-1]
    # endIndex puede faltar por tipado "total=False"; proveemos fallback seguro
    return int(last.get("endIndex", 1))

# ========= Operaciones de escritura =========

# src/clients/gdocs_client.py

def write_to_document(document_id: str, text: str) -> None:
    """
    Borra el contenido (sin tocar el newline final) e inserta `text` al inicio.
    Seguro con retries y chunking.
    """
    MAX_CHARS = 50000  # ⬅️ de 80k a 50k
    docs = build_docs_client()

    # 1) Obtener endIndex
    get_req: HttpRequest = docs.documents().get(documentId=document_id)
    doc_raw: Optional[Dict[str, Any]] = _execute_with_retries(get_req)
    doc: Document = cast(Document, doc_raw)
    end_index: int = _get_end_index(doc)  # p.ej. 123

    # ⚠️ Importante: NO borrar el newline final del segmento raíz
    # Si el doc tiene contenido, end_index >= 2; borramos hasta end_index - 1
    delete_end = max(1, end_index - 1)

    # 2) Delete all (solo si hay algo que borrar)
    if delete_end > 1:
        delete_req: HttpRequest = docs.documents().batchUpdate(
            documentId=document_id,
            body={
                "requests": [
                    {
                        "deleteContentRange": {
                            "range": {"startIndex": 1, "endIndex": delete_end}
                        }
                    }
                ]
            },
        )
        _execute_with_retries(delete_req)

    # 3) Insert (en chunks para evitar timeouts/payloads grandes)
    MAX_CHARS = 80000
    if len(text) <= MAX_CHARS:
        insert_body: Dict[str, Any] = {
            "requests": [
                {"insertText": {"location": {"index": 1}, "text": text}}
            ]
        }
        insert_req: HttpRequest = docs.documents().batchUpdate(
            documentId=document_id, body=insert_body
        )
        _execute_with_retries(insert_req)
    else:
        start = 0
        part = 1
        while start < len(text):
            chunk = text[start:start + MAX_CHARS]
            insert_body = {"requests": [{"insertText": {"location": {"index": 1}, "text": chunk}}]}
            insert_req: HttpRequest = docs.documents().batchUpdate(documentId=document_id, body=insert_body)
            _execute_with_retries(insert_req)
            logger.info(f"✍️ Insertado chunk {part} ({len(chunk)} chars)")
            start += MAX_CHARS
            part += 1
            time.sleep(0.15)  # ⬅️ 150ms para no “aplanar” el backend