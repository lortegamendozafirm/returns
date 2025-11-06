# src/clients/vertex_client.py
import time
from google.api_core import exceptions as gex
from vertexai.preview.generative_models import GenerativeModel, Part
from src.auth import init_vertex_ai
from src.settings import settings
from src.utils.logger import get_logger
logger = get_logger(__name__)

def _call_with_retry(make_call, *, desc: str, retries: int = 6, first_wait: float = 3.0, base: float = 2.0):
    wait = first_wait
    for attempt in range(1, retries + 1):
        try:
            return make_call()
        except (gex.ResourceExhausted, gex.ServiceUnavailable, gex.DeadlineExceeded) as e:
            if attempt == retries:
                logger.error(f"❌ {desc}: agotados {retries} intentos: {e}")
                raise
            logger.warning(f"🔁 {desc}: {e.__class__.__name__} ({attempt}/{retries}). "
                           f"Durmiendo {wait:.1f}s…")
            time.sleep(wait)
            wait = min(wait * base, 30.0)
        except Exception:
            # Errores no-retriables
            raise

def generate_text(prompt: str, *, model_id: str | None = None) -> str:
    init_vertex_ai()
    mdl = model_id or settings.vertex_model_id
    logger.info(f"🤖 Solicitando respuesta a modelo {mdl}...")
    def _do():
        model = GenerativeModel(mdl)
        resp = model.generate_content(prompt)
        return resp.text or ""
    return _call_with_retry(_do, desc=f"generate_text({mdl})") or ""

def generate_text_with_files(prompt: str, gcs_uris: list[str], *, model_id: str | None = None) -> str:
    init_vertex_ai()
    mdl = model_id or settings.vertex_model_id
    logger.info(f"🤖 Modelo {mdl} con {len(gcs_uris)} archivo(s) adjunto(s)...")
    def _do():
        model = GenerativeModel(mdl)
        parts = [prompt] + [Part.from_uri(uri, mime_type="application/pdf") for uri in gcs_uris]
        resp = model.generate_content(parts)
        return resp.text or ""
    return _call_with_retry(_do, desc=f"generate_text_with_files({mdl})") or ""

def generate_json_with_files(prompt: str, gcs_uris: list[str], *, model_id: str | None = None) -> str:
    init_vertex_ai()
    mdl = model_id or settings.vertex_model_id
    logger.info(f"🤖 (JSON) Modelo {mdl} con {len(gcs_uris)} archivo(s) adjunto(s)...")
    def _do():
        model = GenerativeModel(mdl, generation_config={"response_mime_type": "application/json"})
        parts = [prompt] + [Part.from_uri(uri, mime_type="application/pdf") for uri in gcs_uris]
        resp = model.generate_content(parts)
        return resp.text or "{}"
    return _call_with_retry(_do, desc=f"generate_json_with_files({mdl})") or ""

def generate_text_from_files_map_reduce(
    system_text: str,
    base_prompt: str,
    chunk_uris: list[str],
    params: dict,
    *,
    map_model_id: str | None = None,
    reduce_model_id: str | None = None,
) -> str:
    """MAP con modelo ligero (Flash) y REDUCE con uno más fuerte (Pro)."""
    map_mdl = map_model_id or settings.vertex_model_id          # por defecto Flash
    red_mdl = reduce_model_id or settings.vertex_model_id_pro    # por defecto Pro

    partials: list[str] = []
    total = len(chunk_uris)
    for i, uri in enumerate(chunk_uris, start=1):
        sub_prompt = (
            f"[SYSTEM]\n{system_text}\n\n"
            f"[PROMPT_BASE]\n{base_prompt}\n\n"
            f"[INPUT_CHUNK {i}/{total}]\n(Usa ÚNICAMENTE el PDF adjunto en esta parte)\n\n"
            f"[PARAMS]\n{params}\n"
        )
        logger.info(f"🗺️ MAP {i}/{total} ({map_mdl})")
        partial = generate_text_with_files(sub_prompt, [uri], model_id=map_mdl)
        partials.append(f"### CHUNK {i}\n{partial}")

    reduce_prompt = (
        f"[SYSTEM]\n{system_text}\n\n"
        f"[PROMPT_BASE]\n{base_prompt}\n\n"
        f"[PARTIALS]\n" + "\n\n".join(partials) + "\n\n"
        "Instrucción: Fusiona y deduplica los resultados anteriores en una sola salida final, "
        "respetando formato y criterios de PROMPT_BASE/PARAMS. No inventes."
    )
    logger.info(f"🧩 REDUCE ({red_mdl})")
    return generate_text(reduce_prompt, model_id=red_mdl)
