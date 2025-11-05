# src/services/back_questions.py
from __future__ import annotations
from io import BytesIO
from typing import List, Dict, Any
import json
import re

from PyPDF2 import PdfReader, PdfWriter

from src.clients.drive_client import assert_sa_has_access, parse_drive_url_to_id, download_file_bytes
from src.clients.gcs_client import upload_bytes
from src.clients.gdocs_client import get_document_content, write_to_document
from src.clients.vertex_client import generate_text_with_files, generate_text_from_files_map_reduce
from src.services.pdf_processing import _to_gcs_chunks  # reutilizamos
from src.settings import settings
from src.utils.logger import get_logger

logger = get_logger(__name__)

_VARIANTS = [
    r"preguntas?\s+de\s+regreso",
    r"preguntas?\s+de\s+seguimiento",
    r"preguntas?\s+para\s+el\s+cliente",
    r"seguimiento",
    r"back\s*questions?",
    r"follow[-\s]?up",
    r"preguntas?\s+pendientes?",
]

def _extract_sample_pdf_bytes(data: bytes, take_first: int, take_last: int) -> bytes:
    r = PdfReader(BytesIO(data))
    n = len(r.pages)
    w = PdfWriter()
    first_count = min(take_first, n)
    for i in range(first_count):
        w.add_page(r.pages[i])
    last_count = min(take_last, n - first_count)
    for i in range(n - last_count, n):
        if i >= first_count:  # evita duplicados si n < take_first + take_last
            w.add_page(r.pages[i])
    out = BytesIO()
    w.write(out)
    return out.getvalue()

def _detect_back_questions_via_model(sample_gs: List[str]) -> List[Dict[str, Any]]:
    # Prompt de detección (Flash). Pedimos JSON estricto.
    prompt = """
Eres un extractor de 'Preguntas de regreso' en documentos legales.
Busca secciones y encabezados que indiquen preguntas para el cliente, seguimiento o back questions.
Sin inventar, devuelve JSON estricto:

{
  "questions": [
    {"id": "q1", "text": "<pregunta exactamente como aparece>", "page_hint": <int|null>, "section_heading": "<encabezado_o_null>"}
  ]
}

Reglas:
- Incluye solo preguntas (frases terminadas en '?', bullets con intención interrogativa, o marcadas bajo encabezados relevantes).
- Acepta variantes: "Preguntas de regreso", "Preguntas de seguimiento", "Preguntas para el cliente", "Seguimiento", "Back questions", "Follow-up", etc.
- 'page_hint' si el texto sugiere la página; si no, null.
- Máximo 50 preguntas.
"""
    raw = generate_text_with_files(prompt, sample_gs, model_id=settings.vertex_model_id)
    try:
        data = json.loads(raw)
        questions = data.get("questions", [])
        # limpieza mínima
        out = []
        for idx, q in enumerate(questions, 1):
            txt = (q.get("text") or "").strip()
            if not txt:
                continue
            # filtro rápido si no luce como pregunta pero está en sección válida: permitimos por variantes
            if "?" not in txt:
                # deja pasar si encabeza por variantes
                heading = (q.get("section_heading") or "").lower()
                if not any(re.search(v, heading) for v in _VARIANTS):
                    continue
            out.append({
                "id": q.get("id") or f"q{idx}",
                "text": txt,
                "page_hint": q.get("page_hint"),
                "section_heading": q.get("section_heading"),
            })
        return out[:50]
    except Exception as e:
        logger.warning(f"No se pudo parsear JSON de detección, intento fallback. Error: {e}")
        # Fallback: tratar de extraer líneas con '?' del texto crudo (si llegase con markup)
        # Para no alargar, devolvemos vacío; el caller hará fallback global.
        return []

def _answer_one_question_over_full_pdf(
    *, question_text: str, system_text: str, base_prompt: str, all_pdf_gs: List[str], params: Dict[str, Any]
) -> str:
    # Inyectamos la pregunta como instrucción explícita.
    enriched_params = dict(params or {})
    enriched_params["question"] = question_text
    enriched_params["objetivo"] = "responder_pregunta_de_regreso"
    # Pro: mejor para razonamiento largo
    answer = generate_text_from_files_map_reduce(
        system_text, base_prompt, all_pdf_gs, enriched_params, model_id=settings.vertex_model_id_pro
    )
    return answer

def _write_qas_to_doc(output_doc_id: str, qas: List[Dict[str, str]]) -> None:
    lines = []
    lines.append("# Respuestas\n")
    for i, qa in enumerate(qas, 1):
        lines.append(f"## {i}. {qa['question'].strip()}")
        lines.append("")
        lines.append(qa["answer"].strip() or "_(sin respuesta)_")
        lines.append("")
    write_to_document(output_doc_id, "\n".join(lines))

def process_back_questions_job(
    *,
    system_instructions_doc_id: str,
    base_prompt_doc_id: str,
    pdf_url: str,
    output_doc_id: str,
    drive_file_id: str | None,
    sampling_first_pages: int,
    sampling_last_pages: int,
    additional_params: Dict[str, Any],
) -> Dict[str, Any]:
    logger.info("🏁 Back-Questions: inicio de job.")
    # Acceso a Docs
    for fid in (system_instructions_doc_id, base_prompt_doc_id, output_doc_id):
        assert_sa_has_access(fid)
    system_text = get_document_content(system_instructions_doc_id)
    base_prompt = get_document_content(base_prompt_doc_id)

    # Resolver PDF y bytes locales
    if pdf_url.startswith("gs://"):
        gs_uris_full = [pdf_url]
        bytes_local = None
        # para sample necesitamos bytes → descargamos vía GCS client si lo tuvieras.
        # Para simplificar, si es gs:// y no tenemos bytes, solo usaremos el mismo URI con rangos cargados previamente.
        # Recomendado: si pdf_url es gs://, también pasa drive_file_id cuando lo tengas.
        raise RuntimeError("Para detección por páginas en gs:// se requiere bytes locales. Usa drive_file_id o URL de Drive.")
    else:
        fid = drive_file_id or parse_drive_url_to_id(pdf_url)
        if not fid:
            raise ValueError("pdf_url no es gs:// y no se pudo extraer drive_file_id.")
        assert_sa_has_access(fid, use_docs_api=False)
        bytes_local = download_file_bytes(fid)

    # Conteo de páginas y preparación all_pdf_gs (map-reduce si es grande)
    reader = PdfReader(BytesIO(bytes_local))
    n_pages = len(reader.pages)
    if n_pages < 80:
        logger.info(f"PDF con {n_pages} páginas (<80). Usando pipeline existente.")
        from src.services.pdf_processing import process_pdf_documents
        return process_pdf_documents(
            system_instructions_doc_id=system_instructions_doc_id,
            base_prompt_doc_id=base_prompt_doc_id,
            pdf_url=pdf_url,
            output_doc_id=output_doc_id,
            drive_file_id=drive_file_id,
            additional_params=additional_params or {},
        )

    # 1) Sample P40 + U40 para detección
    take_first = max(1, sampling_first_pages or settings.backq_first_pages_default)
    take_last = max(1, sampling_last_pages or settings.backq_last_pages_default)
    sample_bytes = _extract_sample_pdf_bytes(bytes_local, take_first=take_first, take_last=take_last)
    sample_uri = upload_bytes(settings.pdf_staging_bucket or "", sample_bytes, suffix=".pdf")
    questions = _detect_back_questions_via_model([sample_uri])

    if not questions:
        logger.info("No se detectaron preguntas de regreso. Fallback a pipeline general.")
        from src.services.pdf_processing import process_pdf_documents
        return process_pdf_documents(
            system_instructions_doc_id=system_instructions_doc_id,
            base_prompt_doc_id=base_prompt_doc_id,
            pdf_url=pdf_url,
            output_doc_id=output_doc_id,
            drive_file_id=drive_file_id,
            additional_params=additional_params or {},
        )

    # 2) Preparar ALL PDF como gs:// chunks (map-reduce)
    all_pdf_gs = _to_gcs_chunks(bytes_local)

    # 3) Responder una por una
    qas: List[Dict[str, str]] = []
    for q in questions:
        q_text = q["text"]
        logger.info(f"→ respondiendo: {q_text[:80]}...")
        ans = _answer_one_question_over_full_pdf(
            question_text=q_text,
            system_text=system_text,
            base_prompt=base_prompt,
            all_pdf_gs=all_pdf_gs,
            params=additional_params or {},
        )
        qas.append({"question": q_text, "answer": ans})

    # 4) Escribir resultados (Q → A)
    _write_qas_to_doc(output_doc_id, qas)

    output_link = f"https://docs.google.com/document/d/{output_doc_id}/edit"
    logger.info("✅ Back-Questions completado.")
    return {"status": "success", "message": "Q/A escritos en el documento.", "output_doc_link": output_link}
