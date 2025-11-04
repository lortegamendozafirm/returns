# ------------------------------------------------------------------------------
# Dockerfile - brain (FastAPI + Vertex AI + Google Docs) - Python 3.11
# Imagen final ≪ 1GB (slim), sin root, uvicorn como servidor
# ------------------------------------------------------------------------------
FROM python:3.11-slim

# Seguridad/ergonomía
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080 \
    PYTHONPATH=/app

# (Opcional) Dependencias del sistema mínimas; wheels de grpcio/aiplatform suelen alcanzar.
# Si alguna wheel faltara en tu plataforma, descomenta build tools:
# RUN apt-get update && apt-get install -y --no-install-recommends \
#     build-essential gcc \
#  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Instalar deps primero (mejor cache)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

# Copiar el código
COPY src ./src

# No copiamos .env al contenedor (se configuran env vars en Cloud Run)
# EXPOSE no es necesario para Cloud Run, pero no hace daño:
EXPOSE 8080

# Ejecutar como usuario no-root
RUN useradd -u 1001 -m appuser
USER 1001

# Comando de arranque (Cloud Run inyecta $PORT)
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8080"]
