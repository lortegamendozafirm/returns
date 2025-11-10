# tests/test_settings_sanity.py
import os
import json
import pytest
from src.settings import settings

def test_core_project_envs_present():
    assert settings.gcp_project_id, "GCP_PROJECT_ID vacío"
    assert settings.gcp_location, "GCP_LOCATION vacío"

def test_workspace_basics():
    # Bucket staging requerido por el flujo
    assert settings.pdf_staging_bucket, "PDF_STAGING_BUCKET vacío"

def test_models_present():
    assert settings.vertex_model_id, "VERTEX_MODEL_ID vacío"
    assert settings.vertex_model_id_pro, "VERTEX_MODEL_ID_PRO vacío"
    assert settings.map_model_id, "MAP_MODEL_ID vacío"
    assert settings.reduce_model_id, "REDUCE_MODEL_ID vacío"

def test_pdf_knobs():
    assert settings.pdf_max_pages_per_chunk >= 5
    assert settings.backq_first_pages_default >= 1
    assert settings.backq_last_pages_default >= 1

def test_router_knobs():
    assert settings.backq_strategy in ("hybrid", "per_question")
    assert settings.backq_k_top_chunks >= 1
    assert settings.backq_min_cover >= 1
    assert settings.backq_chunk_cap >= 1
    assert settings.backq_throttle_s >= 0

def test_base_prompt_ids_json_parseable_and_has_default():
    mp = settings.base_prompt_ids()
    assert isinstance(mp, dict)
    # Debe existir 'default' según tu .env actual
    assert "default" in mp, "BASE_PROMPT_IDS_JSON debe incluir 'default'"

def test_base_prompt_ids_json_is_valid_json_string():
    # Valida que el env sea un JSON parseable (si está seteado)
    raw = os.getenv("BASE_PROMPT_IDS_JSON")
    if not raw:
        pytest.skip("BASE_PROMPT_IDS_JSON no seteado")
    try:
        parsed = json.loads(raw)
        assert isinstance(parsed, dict)
    except Exception as e:
        pytest.fail(f"BASE_PROMPT_IDS_JSON inválido: {e}")
