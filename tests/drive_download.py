from src.clients.drive_client import download_file_bytes
from src.utils.logger import get_logger
import argparse
import hashlib

log = get_logger(__name__)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--file-id", required=True)
    args = ap.parse_args()

    data = download_file_bytes(args.file_id)
    sha = hashlib.sha256(data).hexdigest()[:16]
    log.info(f"✅ Drive get_media OK | bytes={len(data)} | sha256={sha}")
    print("OK")
