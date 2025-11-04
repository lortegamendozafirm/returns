# src/services/pdf_processing.py
from __future__ import annotations
from typing import Dict, List
from io import BytesIO

from PyPDF2 import PdfReader, PdfWriter

from src.clients.gdocs_client import get_document_content, write_to_document
from src.clients.vertex_client import generate_text_with_files, generate_text_from_files_map_reduce
from src.clients.drive_client import (
    assert_sa_has_access, parse_drive_url_to_id, download_file_bytes
)
from src.clients.gcs_client import upload_bytes
from src.utils.logger import get_logger
from src.settings import settings

logger = get_logger(__name__)

def _split_pdf_bytes(data: bytes, pages_per_chunk: int) -> List[bytes]:
    reader = PdfReader(BytesIO(data))
    n = len(reader.pages)
    if n <= pages_per_chunk:
        return [data]
    chunks: List[bytes] = []
    for start in range(0, n, pages_per_chunk):
        end = min(start + pages_per_chunk, n)
        w = PdfWriter()
        for i in range(start, end):
            w.add_page(reader.pages[i])
        out = BytesIO()
        w.write(out)
        chunks.append(out.getvalue())
    return chunks

def _to_gcs_chunks(data: bytes) -> List[str]:
    if not settings.pdf_staging_bucket:
        raise RuntimeError("Falta PDF_STAGING_BUCKET en configuración.")
    pages_per_chunk = max(5, settings.pdf_max_pages_per_chunk)
    reader = PdfReader(BytesIO(data))
    if len(reader.pages) <= pages_per_chunk:
        return [upload_bytes(settings.pdf_staging_bucket, data, suffix=".pdf")]
    uris: List[str] = []
    for chunk in _split_pdf_bytes(data, pages_per_chunk):
        uris.append(upload_bytes(settings.pdf_staging_bucket, chunk, suffix=".pdf"))
    return uris

def build_prompt_for_pdf(system_text: str, base_prompt: str, params: Dict[str, object]) -> str:
    parts = []
    if system_text.strip():
        parts.append(f"[SYSTEM]\n{system_text.strip()}\n")
    if base_prompt.strip():
        parts.append(f"[PROMPT_BASE]\n{base_prompt.strip()}\n")
    if params:
        parts.append(f"[PARAMS]\n{params}\n")
    parts.append("Usa únicamente el/los PDF(s) adjunto(s) como fuente. No inventes.")
    return "\n".join(parts).strip()

def process_pdf_documents(
    *,
    system_instructions_doc_id: str,
    base_prompt_doc_id: str,
    pdf_url: str,
    output_doc_id: str,
    drive_file_id: str | None = None,
    additional_params: Dict[str, object] = {},
) -> dict:
    logger.info("🚀 Iniciando proceso (PDF → Gemini → Doc)...")

    # Pre-check de acceso a Docs (system/base/output)
    for fid in (system_instructions_doc_id, base_prompt_doc_id, output_doc_id):
        assert_sa_has_access(fid)

    system_text = get_document_content(system_instructions_doc_id)
    base_prompt = get_document_content(base_prompt_doc_id)

    # Resolver a gs://
    gs_uris: List[str]
    if pdf_url.startswith("gs://"):
        gs_uris = [pdf_url]
        bytes_local = None
    else:
        fid = drive_file_id or parse_drive_url_to_id(pdf_url)
        if not fid:
            raise ValueError("pdf_url no es gs:// y no se pudo extraer drive_file_id.")
        assert_sa_has_access(fid, use_docs_api=False)  # archivo binario → Drive API
        bytes_local = download_file_bytes(fid)
        if not settings.pdf_staging_bucket:
            raise RuntimeError("Falta PDF_STAGING_BUCKET en configuración.")
        # chunking si es grande
        reader = PdfReader(BytesIO(bytes_local))
        if len(reader.pages) > settings.pdf_max_pages_per_chunk:
            logger.info(f"📚 PDF grande ({len(reader.pages)} páginas). Map-Reduce activado.")
            gs_uris = _to_gcs_chunks(bytes_local)
        else:
            gs_uris = [upload_bytes(settings.pdf_staging_bucket, bytes_local, suffix=".pdf")]

    prompt_text = build_prompt_for_pdf(system_text, base_prompt, additional_params)

    # Llamada al modelo
    if len(gs_uris) == 1:
        ai_output = generate_text_with_files(prompt_text, gs_uris)
    else:
        ai_output = generate_text_from_files_map_reduce(system_text, base_prompt, gs_uris, additional_params)

    # Escribir resultado
    write_to_document(output_doc_id, ai_output or "")
    output_link = f"https://docs.google.com/document/d/{output_doc_id}/edit"
    logger.info("✅ Proceso PDF completado.")
    return {
        "status": "success",
        "message": "El resultado de la IA fue escrito correctamente en el documento.",
        "output_doc_link": output_link,
    }
