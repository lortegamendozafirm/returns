# src/domain/schemas.py
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional

class ProcessRequest(BaseModel):
    system_instructions_doc_id: str
    base_prompt_doc_id: str
    input_doc_id: str
    output_doc_id: str
    additional_params: Dict[str, Any] = Field(default_factory=dict)

class ProcessResponse(BaseModel):
    status: str
    message: str
    output_doc_link: str

# ✅ Nuevo: igual al anterior, pero reemplaza input_doc_id por pdf_url (+ opcional drive_file_id)
class ProcessRequestPDF(BaseModel):
    system_instructions_doc_id: str
    base_prompt_doc_id: str
    pdf_url: str  # e.g. https://drive.google.com/file/d/<ID>/view?...  ó  gs://bucket/obj.pdf
    output_doc_id: str
    drive_file_id: Optional[str] = None
    additional_params: Dict[str, Any] = Field(default_factory=dict)


class ProcessBackQuestionsEnqueueRequest(BaseModel):
    system_instructions_doc_id: str
    base_prompt_doc_id: str
    pdf_url: str
    output_doc_id: str
    drive_file_id: Optional[str] = None
    sampling_first_pages: Optional[int] = None
    sampling_last_pages: Optional[int] = None
    additional_params: Dict[str, Any] = Field(default_factory=dict)

class TaskRunBackQuestionsPayload(BaseModel):
    # mismo payload que arriba; lo separo por claridad
    system_instructions_doc_id: str
    base_prompt_doc_id: str
    pdf_url: str
    output_doc_id: str
    drive_file_id: Optional[str] = None
    sampling_first_pages: Optional[int] = None
    sampling_last_pages: Optional[int] = None
    sheet_id: str
    row: int   # 1-based
    col: int   # 1-based (link); status en col+1
    additional_params: Dict[str, Any] = {}

class AcceptedResponse(BaseModel):
    status: str = "accepted"
    message: str = "Job encolado. Se procesará en background."
    task_name: Optional[str] = None
