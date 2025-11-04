from src.clients.gcs_client import upload_bytes
from src.settings import settings
from src.utils.logger import get_logger

log = get_logger(__name__)

if __name__ == "__main__":
    assert settings.pdf_staging_bucket, "Falta PDF_STAGING_BUCKET"
    uri = upload_bytes(settings.pdf_staging_bucket, b"hello-pdf", suffix=".pdf")
    log.info(f"✅ GCS upload OK | {uri}")
    print(uri)
