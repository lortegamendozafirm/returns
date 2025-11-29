# src/api/routes.py
from fastapi import APIRouter
from src.domain.schemas import TaskRunBackQuestionsPayload
from src.services.back_questions import process_back_questions_job
from src.settings import settings

router = APIRouter()

@router.post("/_tasks/process-pdf-back-questions-run")
def process_pdf_back_questions_run(req: TaskRunBackQuestionsPayload):
    return process_back_questions_job(
        system_instructions_doc_id=req.system_instructions_doc_id,
        base_prompt_doc_id=req.base_prompt_doc_id,
        pdf_url=req.pdf_url,
        output_doc_id=req.output_doc_id,
        drive_file_id=req.drive_file_id,
        sampling_first_pages=req.sampling_first_pages or settings.backq_first_pages_default,
        sampling_last_pages=req.sampling_last_pages or settings.backq_last_pages_default,
        sheet_id=req.sheet_id,
        row=req.row,
        col=req.col,
        additional_params=req.additional_params or {},
    )

