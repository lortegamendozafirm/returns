# tests/test_integration_connectors.py
import os
import pytest
from googleapiclient.errors import HttpError

RUN = os.getenv("RUN_INTEGRATION") == "1"

pytestmark = pytest.mark.skipif(not RUN, reason="Set RUN_INTEGRATION=1 para ejecutar estas pruebas.")

from src.auth import get_all_clients, init_vertex_ai
from src.settings import settings
from src.clients.gcs_client import upload_bytes

def test_vertex_init_ok():
    ok = init_vertex_ai()
    assert ok is True

def test_docs_and_drive_clients_can_auth():
    clients = get_all_clients()
    assert clients["vertex_initialized"] is True
    assert clients["drive"] is not None
    assert clients["docs"] is not None

def test_can_read_existing_doc_if_provided():
    doc_id = settings.existing_doc_id
    if not doc_id:
        pytest.skip("EXISTING_DOC_ID no seteado en .env")
    service = get_all_clients()["docs"]
    try:
        # pedir campos mínimos
        doc = service.documents().get(documentId=doc_id).execute()
        assert "title" in doc
    except HttpError as e:
        pytest.fail(f"No se pudo leer el Doc {doc_id}: {e}")

def test_can_upload_small_blob_to_staging_bucket():
    bucket = settings.pdf_staging_bucket
    assert bucket, "PDF_STAGING_BUCKET requerido"
    gs_uri = upload_bytes(bucket, b"ping", suffix=".txt")
    assert gs_uri.startswith("gs://"), f"URI inesperada: {gs_uri}"
