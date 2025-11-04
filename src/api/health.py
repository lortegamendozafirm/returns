# src/api/health.py
from fastapi import APIRouter
from googleapiclient.errors import HttpError
from src.utils.logger import get_logger
from src.auth import init_vertex_ai
from src.clients.gdocs_client import get_document_content

router = APIRouter()
log = get_logger(__name__)

@router.get("/health")
def health(doc_id: str | None = None):
    checks = {"app": "ok"}
    # Vertex init (no llama al modelo)
    try:
        init_vertex_ai()
        checks["vertex"] = "ok"
    except Exception as e:
        checks["vertex"] = f"error: {e.__class__.__name__}"

    # Lectura opcional de un Doc para validar credenciales y permisos
    if doc_id:
        try:
            _ = get_document_content(doc_id)[:50]
            checks["docs_read"] = "ok"
        except HttpError as e:
            checks["docs_read"] = f"http_error: {e.resp.status}"
        except Exception as e:
            checks["docs_read"] = f"error: {e.__class__.__name__}"

    return {"status": "healthy" if all(v == "ok" or k == "app" for k, v in checks.items()) else "degraded",
            "checks": checks}
