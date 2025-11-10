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

def set_values(sheet_id: str, a1_range: str, values: list[list[str]], *, value_input_option: str = "RAW"):
    """
    Escribe valores en un rango A1 específico (update, no append).
    values: matriz (filas x columnas).
    """
    sheets = build_sheets_client()
    logger.info(f"📝 Escribiendo rango {a1_range} en Sheet {sheet_id}...")
    try:
        sheets.spreadsheets().values().update(
            spreadsheetId=sheet_id,
            range=a1_range,
            valueInputOption=value_input_option,
            body={"values": values},
        ).execute()
        logger.info("✅ Rango actualizado correctamente.")
    except Exception as e:
        logger.error(f"Error al escribir en Sheet {sheet_id}, rango {a1_range}: {e}")
        raise