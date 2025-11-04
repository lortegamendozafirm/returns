from src.clients.gdocs_client import write_to_document
from src.utils.logger import get_logger
import argparse 
import datetime as dt

log = get_logger(__name__)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--doc-id", required=True)
    args = ap.parse_args()
    text = f"Smoke test OK {dt.datetime.utcnow():%Y-%m-%d %H:%M:%S} UTC\n" * 5
    write_to_document(args.doc_id, text)
    log.info("✅ Docs write small OK")
    print("OK")
