# tests/docs_write_stress.py
from src.clients.gdocs_client import write_to_document
from src.utils.logger import get_logger
import argparse 
import time
import datetime as dt

log = get_logger(__name__)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--doc-id", required=True)
    ap.add_argument("--runs", type=int, default=5)
    args = ap.parse_args()

    base = (
        "### Resumen generado\n"
        "- Punto A\n- Punto B\n- Punto C\n\n"
        "Texto largo " * 4000 + "\n"
    )

    for i in range(1, args.runs + 1):
        text = f"[Run {i} @ {dt.datetime.utcnow():%H:%M:%S} UTC]\n\n" + base
        log.info(f"🏁 Escritura {i}/{args.runs} (chars={len(text)})…")
        write_to_document(args.doc_id, text)
        time.sleep(0.5)

    log.info("✅ Stress test Docs OK")
    print("OK")
