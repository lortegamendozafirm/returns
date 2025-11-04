from src.clients.gdocs_client import write_to_document
from src.utils.logger import get_logger
import argparse

log = get_logger(__name__)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--doc-id", required=True)
    ap.add_argument("--mb", type=float, default=0.2, help="Tamaño aprox del texto")
    args = ap.parse_args()

    # ~0.2 MB de texto (~200k chars aprox) para forzar chunking
    unit = "Lorem ipsum dolor sit amet, consectetur adipiscing elit. " * 50 + "\n"
    text = unit * int(args.mb * 1000)  # aproximado

    write_to_document(args.doc_id, text)
    log.info("✅ Docs write big OK")
    print("OK")
