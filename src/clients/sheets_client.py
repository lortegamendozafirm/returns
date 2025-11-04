# src/clients/sheets_client.py
from src.auth import build_sheets_client
from src.utils.logger import get_logger

logger = get_logger(__name__)

def append_rows(sheet_id: str, rows: list[list[str]], range_: str = "A1"):
    sheets = build_sheets_client()
    logger.info(f"📊 Agregando filas a Google Sheet {sheet_id}...")
    try:
        sheets.spreadsheets().values().append(
            spreadsheetId=sheet_id,
            range=range_,
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values": rows},
        ).execute()
        logger.info("✅ Filas agregadas correctamente.")
    except Exception as e:
        logger.error(f"Error al actualizar Sheet {sheet_id}: {e}")
        raise
