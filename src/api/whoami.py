# src/api/whoami.py
from fastapi import APIRouter
from googleapiclient.errors import HttpError

from src.auth import build_drive_client
from src.settings import settings

router = APIRouter()

@router.get("/whoami")
def whoami():
    # Qué dice tu configuración local
    cfg = {
        "project_id": settings.gcp_project_id,
        "location": settings.gcp_location,
        "auth_mode": "ADC" if settings.use_adc else "SA_JSON",
        "sa_email_from_settings": settings.sa_email or "unknown",
        "credentials_file": settings.google_application_credentials or "none",
        "environment": settings.environment,
    }

    # Qué identidad observa Drive con las credenciales actuales
    try:
        about = build_drive_client().about().get(
            fields="user(emailAddress,displayName)"
        ).execute()
        drive_user = about.get("user", {})
    except HttpError as e:
        drive_user = {"error": f"HttpError {e.resp.status}", "detail": str(e)}

    return {"config": cfg, "drive_user": drive_user}
