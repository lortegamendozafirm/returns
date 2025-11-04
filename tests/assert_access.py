# tests/assert_access.py
import argparse
import sys
from googleapiclient.errors import HttpError

# importa tu logger y helpers reales
from src.utils.logger import get_logger
from src.settings import settings
from src.auth import build_drive_client, build_docs_client
from src.clients.drive_client import assert_sa_has_access

logger = get_logger(__name__)

def log_active_identity():
    # Muestra qué credenciales está usando el proceso
    try:
        import google.auth
        creds, proj = google.auth.default()
        sa_email = getattr(creds, "service_account_email", None)
        logger.info(f"🔑 ADC/SA activa: {sa_email or 'desconocido'} | proyecto={proj} | env.SA_EMAIL={settings.sa_email}")
    except Exception as e:
        logger.warning(f"No pude determinar identidad activa: {e}")

def probe_docs_api(file_id: str):
    docs = build_docs_client()
    logger.info("📄 Probing con Docs API (documents.get)…")
    resp = docs.documents().get(documentId=file_id).execute()
    title = resp.get("title")
    logger.info(f"✅ Docs API OK | title={title}")

def probe_drive_api(file_id: str):
    drive = build_drive_client()
    logger.info("📁 Probing con Drive API (files.get)…")
    resp = drive.files().get(
        fileId=file_id,
        fields="id,name,mimeType,owners,permissions,driveId",
        supportsAllDrives=True,
    ).execute()
    logger.info(
        f"✅ Drive API OK | name={resp.get('name')} | mime={resp.get('mimeType')} | driveId={resp.get('driveId')}"
    )

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--file-id", required=True, help="ID de archivo a probar")
    parser.add_argument("--mode", choices=["docs", "drive", "auto"], default="auto",
                        help="Qué API usar en assert_sa_has_access (docs=Google Doc, drive=binario/PDF, auto=no aplica aquí)")
    args = parser.parse_args()

    log_active_identity()

    # 1) Probes directos para diagnosticar sin el helper
    try:
        probe_docs_api(args.file_id)
    except HttpError as e:
        logger.error(f"❌ Docs API fallo: {e}")
    except Exception as e:
        logger.error(f"❌ Docs API error no-HTTP: {e}")

    try:
        probe_drive_api(args.file_id)
    except HttpError as e:
        logger.error(f"❌ Drive API fallo: {e}")
    except Exception as e:
        logger.error(f"❌ Drive API error no-HTTP: {e}")

    # 2) assert_sa_has_access con la bandera adecuada
    use_docs_api = True if args.mode == "docs" else False if args.mode == "drive" else True
    logger.info(f"🔎 assert_sa_has_access(file_id={args.file_id}, use_docs_api={use_docs_api})")
    try:
        assert_sa_has_access(args.file_id, use_docs_api=use_docs_api)
        logger.info("✅ assert_sa_has_access: OK")
        sys.exit(0)
    except HttpError as e:
        logger.error(f"❌ assert_sa_has_access: HttpError {e}")
        # Mensaje más útil si es 403/404
        detail = getattr(e, "error_details", None) or str(e)
        sa = settings.sa_email or "Service Account (ver logs)"
        logger.error(
            f"ℹ️ Sugerencia: comparte el archivo {args.file_id} con {sa} "
            f"o mueve el archivo a una carpeta ya compartida. Si es atajo, usa el ID del original."
        )
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ assert_sa_has_access: {e}")
        sys.exit(2)

if __name__ == "__main__":
    main()
