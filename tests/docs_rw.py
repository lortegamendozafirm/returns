# tests/docs_rw.py
from __future__ import annotations

import argparse
from datetime import datetime, timezone

from googleapiclient.errors import HttpError

from src.clients.drive_client import assert_sa_has_access
from src.auth import build_docs_client
from src.clients.gdocs_client import get_document_content, write_to_document
from src.utils.logger import get_logger

logger = get_logger(__name__)


def insert_text_top(doc_id: str, text: str) -> None:
    """
    Inserta texto al inicio del documento sin borrar el contenido existente.
    """
    docs = build_docs_client()
    to_insert = text if text.endswith("\n") else text + "\n"
    requests = [{"insertText": {"location": {"index": 1}, "text": to_insert}}]
    docs.documents().batchUpdate(documentId=doc_id, body={"requests": requests}).execute()


def main() -> None:
    parser = argparse.ArgumentParser(description="Prueba lectura/escritura Google Docs por ID")
    parser.add_argument("--doc-id", required=True, help="ID del Google Doc a probar")
    parser.add_argument(
        "--write",
        choices=["append", "replace"],
        default=None,
        help="Acción de escritura: 'append' inserta al inicio (no destructivo) | 'replace' reemplaza todo",
    )
    args = parser.parse_args()
    doc_id = args.doc_id

    # 1) Pre-check de acceso con Docs API
    try:
        assert_sa_has_access(doc_id, use_docs_api=True)
        logger.info(f"✅ Acceso verificado para Doc {doc_id}")
    except HttpError as e:
        logger.error(f"❌ Sin acceso al Doc {doc_id}: {e}")
        raise SystemExit(1)

    # 2) Lectura
    try:
        content = get_document_content(doc_id)
        snippet = content[:600].rstrip()
        logger.info(f"📖 Primeros 600 chars del Doc {doc_id}:\n{snippet}\n")
    except HttpError as e:
        logger.error(f"❌ Error leyendo Doc {doc_id}: {e}")
        raise SystemExit(1)

    # 3) Escritura (opcional)
    if args.write:
        try:
            ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S %Z")
            if args.write == "append":
                line = f"🔧 Test append-top — {ts}"
                insert_text_top(doc_id, line)
                logger.info(f"✅ Append-top realizado en {doc_id}")
            elif args.write == "replace":
                body = (
                    f"🧪 Test REPLACE — {ts}\n\n"
                    "Este contenido reemplaza por completo el documento para validar la API de escritura.\n"
                    "- Línea 1\n- Línea 2\n- Línea 3\n"
                )
                write_to_document(doc_id, body)
                logger.info(f"✅ Replace realizado en {doc_id}")
        except HttpError as e:
            logger.error(f"❌ Error escribiendo en Doc {doc_id}: {e}")
            raise SystemExit(1)


if __name__ == "__main__":
    main()
