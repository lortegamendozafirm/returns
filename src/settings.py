# src/settings.py
from __future__ import annotations
from functools import lru_cache
from typing import Optional, Dict
from pydantic import Field
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    """Configuración central del proyecto regresos/"""

    # --- Identidad del proyecto ---
    gcp_project_id: str = Field(..., env="GCP_PROJECT_ID")
    gcp_location: str = Field("us-central1", env="GCP_LOCATION")

    # --- Cuenta de servicio ---
    sa_email: Optional[str] = Field(None, env="SA_EMAIL")
    google_application_credentials: Optional[str] = Field(None, env="GOOGLE_APPLICATION_CREDENTIALS")
    dwd_subject: Optional[str] = Field(None, env="DWD_SUBJECT")

    # --- Google Workspace / Drive ---
    shared_folder_id: Optional[str] = Field(None, env="SHARED_FOLDER_ID")
    existing_doc_id: Optional[str] = Field(None, env="EXISTING_DOC_ID")
    existing_sheet_id: Optional[str] = Field(None, env="EXISTING_SHEET_ID")
    doc_name: Optional[str] = Field(None, env="DOC_NAME")
    sheet_name: Optional[str] = Field(None, env="SHEET_NAME")

    # --- Sistema / Logs ---
    log_level: str = Field("INFO", env="LOG_LEVEL")
    environment: str = Field("local", env="ENVIRONMENT")

    # --- PDFs / Staging ---
    pdf_staging_bucket: Optional[str] = Field(None, env="PDF_STAGING_BUCKET")
    pdf_max_pages_per_chunk: int = Field(60, env="PDF_MAX_PAGES_PER_CHUNK")
    pdf_use_file_api: bool = Field(True, env="PDF_USE_FILE_API")

    # --- Vertex AI (compat) ---
    vertex_model_id: str = Field("gemini-2.5-flash", env="VERTEX_MODEL_ID")
    vertex_model_id_pro: str = Field("gemini-2.5-pro", env="VERTEX_MODEL_ID_PRO")

    # --- Modelos para el pipeline híbrido ---
    map_model_id: str = Field("gemini-2.5-flash", env="MAP_MODEL_ID")     # rápido (Flash)
    reduce_model_id: str = Field("gemini-2.5-pro", env="REDUCE_MODEL_ID") # calidad (Pro)

    # --- Cloud Tasks (si aplica) ---
    tasks_queue_id: str = Field("back-questions", env="TASKS_QUEUE_ID")
    tasks_handler_base_url: str = Field("", env="TASKS_HANDLER_BASE_URL")
    tasks_oidc_audience: str = Field("", env="TASKS_OIDC_AUDIENCE")

    # --- Back-questions: detección y estrategia ---
    backq_first_pages_default: int = Field(40, env="BACKQ_FIRST_PAGES_DEFAULT")
    backq_last_pages_default: int = Field(40, env="BACKQ_LAST_PAGES_DEFAULT")
    backq_detect_limit: int = Field(100, env="BACKQ_DETECT_LIMIT")
    backq_strategy: str = Field("hybrid", env="BACKQ_STRATEGY")  # "hybrid" | "per_question"

    # --- Routing (router + batch por chunk) ---
    backq_k_top_chunks: int = Field(3, env="BACKQ_K_TOP_CHUNKS")
    backq_min_cover: int = Field(2, env="BACKQ_MIN_COVER")
    backq_chunk_cap: int = Field(20, env="BACKQ_CHUNK_CAP")

    # --- Throttling para llamadas MAP ---
    backq_throttle_s: float = Field(1.0, env="BACKQ_THROTTLE_S")

    # --- Mapping BasePrompts por tipo de visa ---
    base_prompt_ids_json: Optional[str] = Field(None, env="BASE_PROMPT_IDS_JSON")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

    # -------- Helpers --------
    def base_prompt_ids(self) -> Dict[str, str]:
        """Devuelve mapping {tipo_visa_lower: doc_id} desde env JSON; dict vacío si no existe o es inválido."""
        import json
        if not self.base_prompt_ids_json:
            return {}
        try:
            return {str(k).lower(): str(v) for k, v in json.loads(self.base_prompt_ids_json).items()}
        except Exception:
            return {}

    @property
    def use_adc(self) -> bool:
        """True si se usa ADC (Cloud Run/gcloud) en lugar de SA JSON local."""
        return not bool(self.google_application_credentials)

    @property
    def vertex_model(self) -> str:
        """Compatibilidad con código legado que consulta 'vertex_model'."""
        return self.vertex_model_id or "gemini-2.5-flash"

    @property
    def is_local(self) -> bool:
        return self.environment.lower() in ("local", "dev", "development")


@lru_cache()
def get_settings() -> Settings:
    return Settings()

# Instancia singleton
settings = get_settings()
