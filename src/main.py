# src/main.py
from fastapi import FastAPI
from src.api.routes import router as api_router
from src.api.health import router as health_router
from src.api.whoami import router as whoami_router

app = FastAPI(title="AI Doc Processor API")
app.include_router(api_router)
app.include_router(health_router)
app.include_router(whoami_router)
