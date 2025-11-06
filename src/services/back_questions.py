# src/services/back_questions.py
from __future__ import annotations
from io import BytesIO
from typing import List, Dict, Any, Optional
import os
import json
import re
import time

from PyPDF2 import PdfReader, PdfWriter
from google.api_core import exceptions as gex
from src.clients.drive_client import assert_sa_has_access, parse_drive_url_to_id, download_file_bytes
from src.clients.gcs_client import upload_bytes
from src.clients.gdocs_client import get_document_content, write_to_document
from src.clients.gdocs_client import write_qas_native
from src.clients.vertex_client import generate_json_with_files
from src.clients.vertex_client import generate_text_from_files_map_reduce
from src.services.pdf_processing import _to_gcs_chunks  # reutilizamos
from src.settings import settings
from src.utils.logger import get_logger

logger = get_logger(__name__)

_VARIANTS = [
    r"preguntas?\s+de\s+regreso",
    r"preguntas?\s+regreso",
    r"preguntas?\s+de\s+seguimiento",
    r"preguntas?\s+para\s+el\s+cliente",
    r"seguimiento",
    r"back\s*questions?",
    r"follow[-\s]?up",
    r"preguntas?\s+pendientes?",
]

def _detect_back_questions_via_model(sample_gs: List[str], *, max_questions: int) -> List[Dict[str, Any]]:
    prompt = f"""
Eres un extractor de 'Preguntas de regreso' en documentos legales.
Busca secciones y encabezados que indiquen preguntas para el cliente, seguimiento o back questions.
Entrega SOLO JSON válido (sin comentarios, sin texto adicional):

{{
  "questions": [
    {{"id": "q1", "text": "<pregunta exactamente como aparece>", "page_hint": <int|null>, "section_heading": "<encabezado_o_null>"}}
  ]
}}

Reglas:
- Incluye solo preguntas (frases con '?' o bullets interrogativos) o elementos bajo encabezados relevantes.
- Acepta variantes: "Preguntas de regreso", "Preguntas regreso", "Preguntas de seguimiento", "Preguntas para el cliente", "Seguimiento", "Back questions", "Follow-up".
- 'page_hint' si el texto sugiere la página; si no, null.
- Máximo {max_questions} preguntas.
""".strip()

    raw = generate_json_with_files(prompt, sample_gs, model_id=settings.vertex_model_id)  # Flash pero en JSON
    try:
        data = _safe_json_loads(raw)
        questions = data.get("questions", [])
    except Exception as e:
        logger.warning(f"No se pudo parsear JSON de detección (len={len(raw)}). Error: {e}")
        questions = []

    out = []
    for idx, q in enumerate(questions, 1):
        txt = (q.get("text") or "").strip()
        if not txt:
            continue
        if "?" not in txt:
            heading = (q.get("section_heading") or "").lower()
            if not any(re.search(v, heading, re.I) for v in _VARIANTS):
                continue
        out.append({
            "id": q.get("id") or f"q{idx}",
            "text": txt,
            "page_hint": q.get("page_hint"),
            "section_heading": q.get("section_heading"),
        })
    return out[:max_questions]

def _detect_back_questions_regex(sample_bytes: bytes) -> List[Dict[str, Any]]:
    r = PdfReader(BytesIO(sample_bytes))
    buf = []
    for p in range(len(r.pages)):
        try:
            buf.append(r.pages[p].extract_text() or "")
        except Exception:
            buf.append("")
    txt = "\n".join(buf)

    # Encuentra el bloque a partir de encabezados probables
    if any(re.search(v, txt, re.I) for v in _VARIANTS):
        # Extrae líneas con signo de interrogación
        qs = []
        for line in txt.splitlines():
            s = line.strip()
            if not s:
                continue
            # preguntas típicas “1 ¿…?” o “¿…?”
            if re.search(r"¿.+\?", s):
                qs.append(s)
        return [{"id": f"q{i+1}", "text": q, "page_hint": None, "section_heading": None} for i, q in enumerate(qs)]
    return []


def _resolve_base_prompt_doc_id(
    *, explicit_base_prompt_doc_id: str | None,
    visa_type: str | None,
    base_prompt_ids_from_req: Dict[str, str] | None
) -> str | None:
    """
    Prioridad:
    1) Si viene base_prompt_doc_id explícito en el request → úsalo.
    2) Si viene mapping en el request (additional_params.base_prompt_ids) + visa_type → úsalo.
    3) Si hay mapping en env (settings.base_prompt_ids_json) + visa_type → úsalo.
    4) Si hay mapping con 'default' → úsalo.
    5) None → caller manejará error si hace falta.
    """
    if explicit_base_prompt_doc_id:
        return explicit_base_prompt_doc_id

    vt = (visa_type or "").strip().lower()
    req_map = { (k or "").lower(): v for k, v in (base_prompt_ids_from_req or {}).items() }
    env_map = settings.base_prompt_ids()

    if vt and vt in req_map:
        return req_map[vt]
    if vt and vt in env_map:
        return env_map[vt]
    if "default" in req_map:
        return req_map["default"]
    if "default" in env_map:
        return env_map["default"]
    return None


def _to_docs_friendly_markdown(md: str) -> str:
    """
    Normaliza un poco el Markdown para que 'se vea bien' pegado en Google Docs:
    - Convierte encabezados a texto claro con líneas en blanco.
    - Convierte bullets '-' o '*' a '• '.
    - Limpia triples backticks en bloques.
    No aplica estilos de Docs (eso sería otro batchUpdate más elaborado).
    """
    lines = []
    for raw in md.splitlines():
        s = raw.rstrip()

        # Headings
        if s.startswith("### "):
            lines.append(s.replace("### ", "").strip())
            lines.append("")  # blank line
            continue
        if s.startswith("## "):
            lines.append(s.replace("## ", "").strip())
            lines.append("") 
            continue
        if s.startswith("# "):
            lines.append(s.replace("# ", "").strip())
            lines.append("")
            continue

        # Bullets
        if s.lstrip().startswith("- "):
            s = "• " + s.lstrip()[2:]
        elif s.lstrip().startswith("* "):
            s = "• " + s.lstrip()[2:]

        # Code fences (remover marcas, dejar contenido plano)
        if s.strip().startswith("```") or s.strip().endswith("```"):
            continue

        lines.append(s)
    # quita espacios finales
    text = "\n".join(lines)
    # compacta saltos excesivos
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() + "\n"


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

def _answer_one_question_over_full_pdf(
    *, question_text: str, system_text: str, base_prompt: str,
    all_pdf_gs: List[str], params: Dict[str, Any]
) -> str:
    # Inyectamos la pregunta como instrucción explícita.
    enriched_params = dict(params or {})
    enriched_params["question"] = question_text
    enriched_params["objetivo"] = "responder_pregunta_de_regreso"

    # MAP con Flash (rápido) + REDUCE con Pro (razonamiento)
    return generate_text_from_files_map_reduce(
        system_text,
        base_prompt,
        all_pdf_gs,
        enriched_params,
        map_model_id=settings.vertex_model_id,        # p.ej. gemini-2.5-flash
        reduce_model_id=settings.vertex_model_id_pro  # p.ej. gemini-2.5-pro
    )


def _split_pdf_to_text_chunks(data: bytes, pages_per_chunk: int) -> List[str]:
    r = PdfReader(BytesIO(data))
    n = len(r.pages)
    chunks = []
    for start in range(0, n, pages_per_chunk):
        end = min(start + pages_per_chunk, n)
        texts = []
        for i in range(start, end):
            try:
                texts.append(r.pages[i].extract_text() or "")
            except Exception:
                pass
        chunks.append("\n".join(texts))
    return chunks

def _select_topk_chunks_for_question(question: str, chunk_texts: List[str], k: int = 4) -> List[int]:
    """
    Selección rápida por coincidencias de palabras clave.
    """
    q = re.sub(r"[^\w\sáéíóúüñÁÉÍÓÚÜÑ]", " ", question.lower())
    tokens = [t for t in q.split() if len(t) > 2]
    scores = []
    for idx, txt in enumerate(chunk_texts):
        t = txt.lower()
        # score simple: conteo de tokens presentes
        sc = sum(t.count(tok) for tok in tokens)
        scores.append((sc, idx))
    scores.sort(reverse=True)
    top = [idx for sc, idx in scores[:k] if sc > 0]
    return top or list(range(0, min(k, len(chunk_texts))))  # fallback si no hubo match


def _extract_first_json_object(raw: str) -> str | None:
    """
    Devuelve el primer objeto JSON balanceado a partir del primer '{'.
    Respeta comillas y escapes. Soporta texto antes/después y fenced code.
    """
    s = (raw or "").strip()
    # quita fences tipo ```json ... ```
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*|\s*```$", "", s, flags=re.I | re.S).strip()

    # busca primer '{'
    start = s.find("{")
    if start == -1:
        return None

    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(s)):
        ch = s[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return s[start:i+1]
    return None

def _safe_json_loads(raw: str) -> dict:
    s = (raw or "").strip()
    # intento directo
    try:
        return json.loads(s)
    except Exception:
        pass
    # intento con extractor balanceado
    frag = _extract_first_json_object(s)
    if frag:
        return json.loads(frag)
    # nada que hacer
    raise ValueError("No se encontró JSON válido en la salida del modelo.")



def process_back_questions_job(
    *,
    system_instructions_doc_id: str,
    base_prompt_doc_id: Optional[str],           # ahora opcional
    pdf_url: str,
    output_doc_id: str,
    drive_file_id: Optional[str],
    sampling_first_pages: int,
    sampling_last_pages: int,
    additional_params: Dict[str, Any],
) -> Dict[str, Any]:
    logger.info("🏁 Back-Questions: inicio de job.")

    # --- Accesos mínimos previos
    # (No asserts sobre base_prompt_doc_id todavía, porque puede resolverse por visa_type)
    for fid in (system_instructions_doc_id, output_doc_id):
        assert_sa_has_access(fid)

    # --- Cargar system y resolver BASE_PROMPT dinámico
    system_text = get_document_content(system_instructions_doc_id)

    visa_type = (additional_params or {}).get("visa_type")
    base_prompt_ids_from_req = (additional_params or {}).get("base_prompt_ids") or {}
    resolved_base_prompt_id = _resolve_base_prompt_doc_id(
        explicit_base_prompt_doc_id=base_prompt_doc_id,
        visa_type=visa_type,
        base_prompt_ids_from_req=base_prompt_ids_from_req
    )
    if not resolved_base_prompt_id:
        raise ValueError("No se pudo resolver base_prompt_doc_id (ni explícito, ni por visa_type, ni por 'default').")

    assert_sa_has_access(resolved_base_prompt_id)
    base_prompt = get_document_content(resolved_base_prompt_id)

    # --- Resolver PDF y obtener bytes locales (para muestreo P40/U40)
    if pdf_url.startswith("gs://"):
        # En tu flujo actual usas Drive; si en algún momento pasas gs://, añade un gcs_client.download_bytes().
        raise RuntimeError("Para muestreo por páginas con 'gs://', implementa gcs_client.download_bytes() o usa Drive.")
    else:
        fid = drive_file_id or parse_drive_url_to_id(pdf_url)
        if not fid:
            raise ValueError("pdf_url no es gs:// y no se pudo extraer drive_file_id.")
        assert_sa_has_access(fid, use_docs_api=False)
        bytes_local = download_file_bytes(fid)

    # --- Conteo de páginas / fallback flujo actual si <80
    reader = PdfReader(BytesIO(bytes_local))
    n_pages = len(reader.pages)
    if n_pages < 80:
        logger.info(f"PDF con {n_pages} páginas (<80). Usando pipeline existente.")
        from src.services.pdf_processing import process_pdf_documents
        return process_pdf_documents(
            system_instructions_doc_id=system_instructions_doc_id,
            base_prompt_doc_id=resolved_base_prompt_id,
            pdf_url=pdf_url,
            output_doc_id=output_doc_id,
            drive_file_id=drive_file_id,
            additional_params=additional_params or {},
        )

    # --- 1) Sample P40 + U40 para detección
    take_first = max(1, sampling_first_pages or settings.backq_first_pages_default)
    take_last  = max(1, sampling_last_pages  or settings.backq_last_pages_default)

    if not settings.pdf_staging_bucket:
        raise RuntimeError("Falta PDF_STAGING_BUCKET en configuración.")

    logger.info(f"📄 PDF n={n_pages} páginas; sample first/last = {take_first}/{take_last}")
    sample_bytes = _extract_sample_pdf_bytes(bytes_local, take_first=take_first, take_last=take_last)
    sample_uri   = upload_bytes(settings.pdf_staging_bucket, sample_bytes, suffix=".pdf")
    logger.info(f"🗂️ Sample subido a: {sample_uri}")

    max_q = int((additional_params or {}).get("detect_limit") or settings.backq_detect_limit)
    questions = _detect_back_questions_via_model([sample_uri], max_questions=max_q)

    if not questions:
        logger.warning("⚠️ Detector ML no devolvió preguntas. Probando fallback regex local sobre el sample…")
        questions = _detect_back_questions_regex(sample_bytes)[:max_q]

    # --- 2) Preparar PDF completo para map-reduce (chunks en GCS)
    all_pdf_gs = _to_gcs_chunks(bytes_local)
    pages_per_chunk = max(5, settings.pdf_max_pages_per_chunk)
    chunk_texts = _split_pdf_to_text_chunks(bytes_local, pages_per_chunk)
    k_top = int((additional_params or {}).get("k_top_chunks") or 4)
    throttle_s = float((additional_params or {}).get("throttle_s") or 1.0)
    # --- 3) Responder pregunta por pregunta
    qas: List[Dict[str, str]] = []
    for idx, q in enumerate(questions, 1):
        q_text = q["text"]
        top_idx = _select_topk_chunks_for_question(q_text, chunk_texts, k=k_top)
        selected_uris = [all_pdf_gs[i] for i in top_idx]
        logger.info(f"→ Respondiendo ({idx}/{len(questions)}): {q_text[:80]}… (chunks {top_idx})")

        try:
            ans = generate_text_from_files_map_reduce(
                system_text, base_prompt, selected_uris,
                {**(additional_params or {}), "question": q_text, "objetivo": "responder_pregunta_de_regreso"},
                map_model_id=settings.vertex_model_id,         # Flash
                reduce_model_id=settings.vertex_model_id_pro,  # Pro
            )
        except gex.ResourceExhausted as e:
            logger.warning(f"⏳ 429 en pregunta {idx}. Reintentando con menos chunks…")
            # degradar a k=2 y/o usar solo Flash como último recurso
            try_uris = selected_uris[:2] if len(selected_uris) > 2 else selected_uris
            try:
                ans = generate_text_from_files_map_reduce(
                    system_text, base_prompt, try_uris,
                    {**(additional_params or {}), "question": q_text, "objetivo": "responder_pregunta_de_regreso"},
                    map_model_id=settings.vertex_model_id,         # Flash
                    reduce_model_id=settings.vertex_model_id,       # REDUCE también Flash (degradación)
                )
            except Exception as e2:
                logger.error(f"❌ Pregunta {idx} falló tras degradación: {e2}")
                ans = "_(No se pudo responder por límite temporal de cuota; intente más tarde)_"
        except Exception as e:
            logger.error(f"❌ Error en pregunta {idx}: {e}")
            ans = "_(error al procesar esta pregunta)_"

        qas.append({"question": q_text, "answer": ans})
        # Pequeño throttle para no golpear rate limits
        time.sleep(throttle_s)
    # --- 4) Armar salida en Markdown y convertirla a texto “amigable” para Docs
    write_qas_native(output_doc_id, title="Respuestas", qas=qas)
    ##############
 
    output_link = f"https://docs.google.com/document/d/{output_doc_id}/edit"
    logger.info("✅ Back-Questions completado.")
    return {"status": "success", "message": "Q/A escritos en el documento.", "output_doc_link": output_link}