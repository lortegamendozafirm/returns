# src/clients/vertex_client.py
from vertexai.preview.generative_models import GenerativeModel, Part
from src.auth import init_vertex_ai
from src.settings import settings
from src.utils.logger import get_logger

logger = get_logger(__name__)

def generate_text(prompt: str) -> str:
    init_vertex_ai()
    model_id = settings.vertex_model_id
    logger.info(f"🤖 Solicitando respuesta a modelo {model_id}...")
    try:
        model = GenerativeModel(model_id)
        response = model.generate_content(prompt)
        logger.debug(f"Respuesta generada ({len(response.text)} caracteres).")
        return response.text
    except Exception as e:
        logger.error(f"Error al generar texto en Vertex AI: {e}")
        raise

# ✅ Nuevo: pasar 1 PDF (GCS URI o varios)
def generate_text_with_files(prompt: str, gcs_uris: list[str]) -> str:
    """
    Envía 'prompt' + uno o más PDFs (gs://...) como partes al modelo.
    """
    init_vertex_ai()
    model_id = settings.vertex_model_id
    logger.info(f"🤖 Modelo {model_id} con {len(gcs_uris)} archivo(s) adjunto(s)...")
    try:
        model = GenerativeModel(model_id)
        parts = [prompt] + [Part.from_uri(uri, mime_type="application/pdf") for uri in gcs_uris]
        response = model.generate_content(parts)
        return response.text
    except Exception as e:
        logger.error(f"Error al generar texto con archivos en Vertex AI: {e}")
        raise

# ✅ Nuevo: patrón Map-Reduce para PDFs grandes
def generate_text_from_files_map_reduce(system_text: str, base_prompt: str,
                                        chunk_uris: list[str], params: dict) -> str:
    """
    MAP: procesa cada chunk por separado (adjuntando su PDF).
    REDUCE: consolida todos los parciales en una sola salida.
    """
    partials: list[str] = []
    total = len(chunk_uris)

    for i, uri in enumerate(chunk_uris, start=1):
        sub_prompt = (
            f"[SYSTEM]\n{system_text}\n\n"
            f"[PROMPT_BASE]\n{base_prompt}\n\n"
            f"[INPUT_CHUNK {i}/{total}]\n(Usa ÚNICAMENTE el PDF adjunto en esta parte)\n\n"
            f"[PARAMS]\n{params}\n"
        )
        partial = generate_text_with_files(sub_prompt, [uri])
        partials.append(f"### CHUNK {i}\n{partial}")

    reduce_prompt = (
        f"[SYSTEM]\n{system_text}\n\n"
        f"[PROMPT_BASE]\n{base_prompt}\n\n"
        f"[PARTIALS]\n" + "\n\n".join(partials) + "\n\n"
        "Instrucción: Fusiona y deduplica los resultados anteriores en una sola salida final, "
        "respetando formato y criterios de PROMPT_BASE/PARAMS. No inventes."
    )
    return generate_text(reduce_prompt)
