# src/clients/gcs_client.py
from google.cloud import storage
from uuid import uuid4
from datetime import datetime

def upload_bytes(bucket_name: str, data: bytes, suffix: str = ".pdf") -> str:
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    path = f"uploads/{datetime.utcnow():%Y/%m/%d}/{uuid4()}{suffix}"
    blob = bucket.blob(path)
    blob.upload_from_string(data, content_type="application/pdf")
    return f"gs://{bucket_name}/{path}"
