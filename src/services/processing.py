# src/services/processing.py
from __future__ import annotations
from typing import Dict

from src.clients.gdocs_client import get_document_content, write_to_document
from src.clients.vertex_client import generate_text
from src.utils.logger import get_logger
from src.clients.drive_client import assert_sa_has_access

logger = get_logger(__name__)

def build_prompt(
    system_text: str,
    base_prompt: str,
    input_text: str,
    params: Dict[str, str] | Dict[str, object],
) -> str:
    # Ensamble simple y claro; fácil de cambiar por plantillas Jinja si luego lo deseas
    prompt = []
    if system_text.strip():
        prompt.append(f"[SYSTEM]\n{system_text.strip()}\n")
    if base_prompt.strip():
        prompt.append(f"[PROMPT_BASE]\n{base_prompt.strip()}\n")
    if input_text.strip():
        prompt.append(f"[INPUT]\n{input_text.strip()}\n")
    if params:
        prompt.append(f"[PARAMS]\n{params}\n")
    return "\n".join(prompt).strip()

def process_documents(
    *,
    system_instructions_doc_id: str,
    base_prompt_doc_id: str,
    input_doc_id: str,
    output_doc_id: str,
    additional_params: Dict[str, str] | Dict[str, object] = {},
) -> dict:
    """
    Flujo principal:
      1) Lee system/base/input.
      2) Construye el prompt final.
      3) Llama a Vertex (Gemini).
      4) Escribe el resultado en el output_doc_id.
      5) Devuelve JSON de confirmación.
    """
    logger.info("🚀 Iniciando proceso de IA (Docs → Gemini → Doc)...")
    # Pre-check de acceso a cada doc
    for fid in (system_instructions_doc_id, base_prompt_doc_id, input_doc_id, output_doc_id):
        assert_sa_has_access(fid)
    # 1) Leer documentos
    system_text = get_document_content(system_instructions_doc_id)
    base_prompt = get_document_content(base_prompt_doc_id)
    input_text = get_document_content(input_doc_id)

    # 2) Ensamblar prompt
    full_prompt = build_prompt(system_text, base_prompt, input_text, additional_params)
    logger.info("🧠 Prompt ensamblado. Solicitando respuesta al modelo...")

    # 3) Vertex AI (Gemini)
    ai_output = generate_text(full_prompt) or ""

    # 4) Escribir en documento de salida
    write_to_document(output_doc_id, ai_output)

    # 5) Respuesta API
    output_link = f"https://docs.google.com/document/d/{output_doc_id}/edit"
    logger.info("✅ Proceso completado.")
    return {
        "status": "success",
        "message": "El resultado de la IA fue escrito correctamente en el documento.",
        "output_doc_link": output_link,
    }
