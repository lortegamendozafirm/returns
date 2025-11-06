# src/settings.py
from __future__ import annotations
import os
from functools import lru_cache
from typing import Optional, Dict
from pydantic import Field
from pydantic_settings  import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """Configuración central del proyecto brain/"""

    # --- Identidad del proyecto ---
    gcp_project_id: str = Field(..., env="GCP_PROJECT_ID") # type: ignore
    gcp_location: str = Field("us-central1", env="GCP_LOCATION") # type: ignore

    # --- Cuenta de servicio --- 
    sa_email: Optional[str] = Field(None, env="SA_EMAIL") # type: ignore
    google_application_credentials: Optional[str] = Field(None, env="GOOGLE_APPLICATION_CREDENTIALS")  # type: ignore
    dwd_subject: Optional[str] = Field(None, env="DWD_SUBJECT") # type: ignore

    # --- Vertex AI ---
    vertex_model_id: str = Field("gemini-2.5-flash", env="VERTEX_MODEL_ID") # type: ignore

    # --- Google Workspace / Drive ---
    shared_folder_id: Optional[str] = Field(None, env="SHARED_FOLDER_ID") # type: ignore
    existing_doc_id: Optional[str] = Field(None, env="EXISTING_DOC_ID") # type: ignore
    existing_sheet_id: Optional[str] = Field(None, env="EXISTING_SHEET_ID") # type: ignore
    doc_name: Optional[str] = Field(None, env="DOC_NAME") # type: ignore
    sheet_name: Optional[str] = Field(None, env="SHEET_NAME") # type: ignore

    # --- Sistema / Logs ---
    log_level: str = Field("INFO", env="LOG_LEVEL") # type: ignore
    environment: str = Field("local", env="ENVIRONMENT") # type: ignore

    pdf_staging_bucket: Optional[str] = Field(None, env="PDF_STAGING_BUCKET") #type: ignore
    pdf_max_pages_per_chunk: int = Field(60, env="PDF_MAX_PAGES_PER_CHUNK") #type: ignore
    pdf_use_file_api: bool = Field(True, env="PDF_USE_FILE_API") #type: ignore

    # NUEVO:
    vertex_model_id_pro: str = Field("gemini-2.5-pro", env="VERTEX_MODEL_ID_PRO") # type: ignore

    # Cloud Tasks
    tasks_queue_id: str = Field("back-questions", env="TASKS_QUEUE_ID") # type: ignore
    tasks_handler_base_url: str = ""      # p.ej. https://<service>-<hash>-uc.a.run.app
    tasks_oidc_audience: str = ""         # si tu servicio requiere auth

    # Back-questions defaults
    backq_first_pages_default: int = Field(40, env="BACKQ_FIRST_PAGES_DEFAULT") # type: ignore
    backq_last_pages_default: int = Field(40, env="BACKQ_LAST_PAGES_DEFAULT") # type: ignore

    base_prompt_ids_json: Optional[str] = Field(None, env="BASE_PROMPT_IDS_JSON")  # type: ignore

    # Límite global de detección
    backq_detect_limit: int = Field(100, env="BACKQ_DETECT_LIMIT")  # type: ignore

    backq_k_top_chunks_default: int = Field(4, env="BACKQ_K_TOP_CHUNKS_DEFAULT") # type: ignore
    vertex_call_spacing_s: float = Field(1.0, env="VERTEX_CALL_SPACING_S") # type: ignore

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

    #model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    
    # --- Helpers de conveniencia ---


    # Helpers:
    def base_prompt_ids(self) -> Dict[str, str]:
        """
        Retorna el mapping {tipo_visa_lower: doc_id} desde env JSON si existe,
        si no, dict vacío (se podrá pasar por request).
        """
        import json
        if not self.base_prompt_ids_json:
            return {}
        try:
            return {k.lower(): v for k, v in json.loads(self.base_prompt_ids_json).items()}
        except Exception:
            return {}
    
    @property
    def use_adc(self) -> bool:
        """Detecta si se debe usar ADC (auth de Cloud Run o gcloud local)"""
        return not bool(self.google_application_credentials)

    @property
    def vertex_model(self) -> str:
        """Devuelve el modelo Vertex AI activo"""
        return self.vertex_model_id or "gemini-2.5-flash"

    @property
    def is_local(self) -> bool:
        """Retorna True si se ejecuta fuera de Cloud Run"""
        return self.environment.lower() in ("local", "dev", "development")
    
    


@lru_cache()
def get_settings() -> Settings:
    """Caché global de configuración"""
    return Settings() # type: ignore

# Instancia singleton
settings = get_settings()
