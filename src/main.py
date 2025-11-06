# src/main.py
from fastapi import FastAPI
from src.api.routes import router as api_router
app = FastAPI(title="Regresos API")
app.include_router(api_router)
