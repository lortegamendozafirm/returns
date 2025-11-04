# src/utils/logger.py
import json
import logging
import os
import sys
from datetime import datetime
from src.settings import settings


class JsonFormatter(logging.Formatter):
    """Formatter que genera logs en formato JSON estructurado (para Cloud Run)."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry, ensure_ascii=False)


def setup_logger():
    """
    Configura un logger global eficiente y contextual.
    - Modo local: salida colorizada, formato humano.
    - Modo Cloud Run: salida JSON estructurada.
    """
    logger = logging.getLogger()
    logger.setLevel(settings.log_level.upper())

    # Limpiar handlers previos (evita duplicados en recargas de FastAPI)
    if logger.hasHandlers():
        logger.handlers.clear()

    # Elegir formato según entorno
    handler = logging.StreamHandler(sys.stdout)
    if settings.is_local:
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    else:
        formatter = JsonFormatter()

    handler.setFormatter(formatter)
    logger.addHandler(handler)

    # Reducir ruido de librerías externas
    for noisy in ("google", "urllib3", "uvicorn", "fastapi"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    logger.info(f"✅ Logger inicializado. Nivel: {settings.log_level.upper()} | Entorno: {settings.environment}")
    return logger


# Singleton global
logger = setup_logger()


def get_logger(name: str) -> logging.Logger:
    """Retorna un logger con nombre contextual."""
    return logging.getLogger(name)
