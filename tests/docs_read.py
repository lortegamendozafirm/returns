from src.clients.gdocs_client import get_document_content
from src.utils.logger import get_logger
import argparse

log = get_logger(__name__)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--doc-id", required=True)
    args = ap.parse_args()
    txt = get_document_content(args.doc_id)
    log.info(f"✅ Docs get OK | chars={len(txt)}")
    print(txt[:250])
