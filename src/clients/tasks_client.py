# src/clients/tasks_client.py
import json
import time
from google.cloud import tasks_v2
from google.protobuf import timestamp_pb2
from urllib.parse import urljoin
from src.settings import settings
from src.utils.logger import get_logger

logger = get_logger(__name__)

def enqueue_http_json_task(*, relative_path: str, payload: dict, delay_seconds: int = 0) -> str:
    client = tasks_v2.CloudTasksClient()
    parent = client.queue_path(settings.gcp_project_id, settings.gcp_location, settings.tasks_queue_id)

    # Resuelve URL destino
    base_url = settings.tasks_handler_base_url.rstrip("/") if settings.tasks_handler_base_url else ""
    if not base_url:
        # Se derivará en ruta: el encolador debe pasar base url en runtime, pero
        # como fallback permitimos ruta absoluta en relative_path.
        logger.warning("TASKS_HANDLER_BASE_URL vacío; asegúrate de enviar relative_path absoluto o definirlo en env.")
    url = urljoin(base_url + "/", relative_path.lstrip("/"))

    task = {
        "http_request": {
            "http_method": tasks_v2.HttpMethod.POST,
            "url": url,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps(payload).encode("utf-8"),
        }
    }

    # OIDC si el servicio requiere auth
    if settings.tasks_oidc_audience:
        task["http_request"]["oidc_token"] = {
            "service_account_email": settings.sa_email,  # ya lo tienes en settings
            "audience": settings.tasks_oidc_audience,
        }

    if delay_seconds > 0:
        ts = timestamp_pb2.Timestamp()
        ts.FromSeconds(int(time.time()) + delay_seconds)
        task["schedule_time"] = ts

    resp = client.create_task(request={"parent": parent, "task": task})
    logger.info(f"Cloud Task encolada: {resp.name}")
    return resp.name
