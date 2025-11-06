# src/clients/gdocs_client.py
from __future__ import annotations

import time
import random
import socket
import ssl
import json
import re

from typing import Any, Dict, List, Optional, TypedDict, cast, Iterator, Tuple
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
            if attempt == max_retries:
                raise
            sleep = delay + random.uniform(0, delay * 0.5)
            kind = "SSL/EOF" if isinstance(e, ssl.SSLError) or _is_ssl_eof(e) else "RED"
            logger.warning(f"🔁 Retry {attempt}/{max_retries} por {kind}: {e}. Esperando {sleep:.1f}s…")
            time.sleep(sleep)
            delay = min(delay * 2, 20)
            # Re-crear cliente en intentos altos por sesión “sucia”
            if attempt >= 3:
                from src.auth import build_docs_client as _b
                _b.cache_clear()
                _b()
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
        return 1
    last = content[-1]
    return int(last.get("endIndex", 1))

# ========= Operaciones de escritura (texto simple) =========

def write_to_document(document_id: str, text: str) -> None:
    """
    Borra el contenido (sin tocar el newline final) e inserta `text` al inicio.
    Seguro con retries y chunking.
    """
    MAX_CHARS = 50_000  # chunks de 50k (estable)
    docs = build_docs_client()

    # 1) Obtener endIndex
    get_req: HttpRequest = docs.documents().get(documentId=document_id)
    doc_raw: Optional[Dict[str, Any]] = _execute_with_retries(get_req)
    doc: Document = cast(Document, doc_raw)
    end_index: int = _get_end_index(doc)

    # 2) Delete all (sin borrar newline raíz)
    delete_end = max(1, end_index - 1)
    if delete_end > 1:
        delete_req: HttpRequest = docs.documents().batchUpdate(
            documentId=document_id,
            body={"requests": [{"deleteContentRange": {"range": {"startIndex": 1, "endIndex": delete_end}}}]},
        )
        _execute_with_retries(delete_req)

    # 3) Insert (chunked)
    if len(text) <= MAX_CHARS:
        insert_body: Dict[str, Any] = {"requests": [{"insertText": {"location": {"index": 1}, "text": text}}]}
        insert_req: HttpRequest = docs.documents().batchUpdate(documentId=document_id, body=insert_body)
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
            time.sleep(0.15)  # 150ms para no “aplanar” el backend

# ========= Parser markdown-ish → bloques semánticos =========

Bullet = Tuple[str, List[str]]   # ("ul"|"ol", items)
Para   = Tuple[str, str]         # ("p", text)
Head   = Tuple[str, int, str]    # ("h", level, text)
Block  = Tuple[str, object]      # union

_ul_pat = re.compile(r"^\s*([\-*•])\s+(.*\S)\s*$")
_ol_pat = re.compile(r"^\s*(\d+)[\.\)]\s+(.*\S)\s*$")
_h_pat  = re.compile(r"^\s*(#{2,6})\s+(.*\S)\s*$")  # ## … ######

def _parse_answer_to_blocks(text: str) -> List[Block]:
    """
    Convierte markdown ligero a bloques:
      - ("h", level, text)  para ##, ###, ####…
      - ("ul", [...])       para -/*/• item
      - ("ol", [...])       para 1. / 1) item
      - ("p", "texto")      para párrafos
    Agrupa listas contiguas y respeta líneas en blanco como separadores.
    """
    lines = [ln.rstrip() for ln in (text or "").splitlines()]
    out: List[Block] = []
    i = 0
    while i < len(lines):
        ln = lines[i]

        # blanco
        if not ln.strip():
            i += 1
            continue

        # encabezado interno
        m_h = _h_pat.match(ln)
        if m_h:
            level = len(m_h.group(1))  # 2..6
            txt = m_h.group(2).strip()
            out.append(("h", level, txt))
            i += 1
            continue

        # ul
        m_ul = _ul_pat.match(ln)
        if m_ul:
            items = []
            while i < len(lines):
                m = _ul_pat.match(lines[i] or "")
                if not m:
                    break
                items.append(m.group(2).strip())
                i += 1
            out.append(("ul", items))
            continue

        # ol
        m_ol = _ol_pat.match(ln)
        if m_ol:
            items = []
            while i < len(lines):
                m = _ol_pat.match(lines[i] or "")
                if not m:
                    break
                items.append(m.group(2).strip())
                i += 1
            out.append(("ol", items))
            continue

        # párrafo
        buf = [ln]
        i += 1
        while (i < len(lines)
               and lines[i].strip()
               and not _ul_pat.match(lines[i])
               and not _ol_pat.match(lines[i])
               and not _h_pat.match(lines[i])):
            buf.append(lines[i])
            i += 1
        out.append(("p", "\n".join(buf).strip()))

    return out

# ========= Escritura con estilos nativos (Q/A) =========

def write_qas_native(document_id: str, title: str, qas: List[Dict[str, str]]) -> None:
    """
    Sobrescribe el Doc con:
      - Título (HEADING_1)
      - Por cada QA:
          * Pregunta (HEADING_2)
          * Respuesta con bloques nativos: párrafos, encabezados internos (HEADING_3+), listas UL/OL
    Hace batchUpdate chunked para evitar requests gigantes.
    """
    docs = build_docs_client()

    # get doc (con retries) para endIndex
    get_req: HttpRequest = docs.documents().get(documentId=document_id)
    doc_raw: Optional[Dict[str, Any]] = _execute_with_retries(get_req)
    doc: Document = cast(Document, doc_raw)
    end_index: int = _get_end_index(doc)

    requests: List[Dict[str, Any]] = []
    cur = 1  # posición corriente en el documento (Docs usa 1-based tras newline raíz)

    def _flush():
        nonlocal requests
        if not requests:
            return
        req: HttpRequest = docs.documents().batchUpdate(documentId=document_id, body={"requests": requests})
        _execute_with_retries(req)
        requests = []

    # 1) Limpiar (sin borrar newline raíz)
    delete_end = max(1, end_index - 1)
    if delete_end > 1:
        requests.append({"deleteContentRange": {"range": {"startIndex": 1, "endIndex": delete_end}}})

    def _insert_text(text: str) -> Tuple[int, int]:
        nonlocal cur, requests
        t = (text or "") + "\n"
        start = cur
        requests.append({"insertText": {"location": {"index": cur}, "text": t}})
        cur += len(t)
        return start, cur

    def _apply_paragraph_style(start: int, end: int, named_style: str):
        requests.append({
            "updateParagraphStyle": {
                "range": {"startIndex": start, "endIndex": end},
                "paragraphStyle": {"namedStyleType": named_style},
                "fields": "namedStyleType"
            }
        })

    def _insert_paragraph(text: str, style: Optional[str] = None):
        start, end = _insert_text(text)
        if style:
            _apply_paragraph_style(start, end, style)

    def _insert_list(items: List[str], preset: str):
        if not items:
            return
        nonlocal cur
        start_block = cur
        for it in items:
            _insert_text(it)
        end_block = cur
        requests.append({
            "createParagraphBullets": {
                "range": {"startIndex": start_block, "endIndex": end_block},
                "bulletPreset": preset
            }
        })

    def _insert_heading(level: int, text: str):
        # Mapear niveles internos: ##→H3, ###→H4, ####→H5 …
        lvl = max(3, min(6, level + 1))
        _insert_paragraph(text, style=f"HEADING_{lvl}")

    # 2) Título
    _insert_paragraph(title, style="HEADING_1")

    # 3) Q/A
    for i, qa in enumerate(qas, 1):
        q_text = (qa.get("question") or "").strip()
        a_text = (qa.get("answer") or "").strip()

        # Pregunta como H2 con numeración
        _insert_paragraph(f"{i}. {q_text}", style="HEADING_2")

        # Bloques de respuesta
        blocks = _parse_answer_to_blocks(a_text)
        for kind, payload in blocks:
            if kind == "p":
                _insert_paragraph(cast(str, payload), style=None)
            elif kind == "ul":
                _insert_list(cast(List[str], payload), preset="BULLET_DISC_CIRCLE_SQUARE")
            elif kind == "ol":
                _insert_list(cast(List[str], payload), preset="NUMBERED_DECIMAL_ALPHA_ROMAN")
            elif kind == "h":
                level, txt = cast(Tuple[int, str], payload)
                _insert_heading(level, txt)

        # Flush defensivo si hay demasiadas operaciones acumuladas
        if len(requests) >= 450:
            logger.info(f"🧾 Flush parcial de batchUpdate ({len(requests)} ops)…")
            _flush()

    # 4) Ejecutar batchUpdate final
    if requests:
        logger.info(f"🧾 Docs nativo: {len(requests)} operaciones totales.")
        _flush()