# src/api/routes.py  (añade imports y el nuevo endpoint)
from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import JSONResponse
from googleapiclient.errors import HttpError
from src.domain.schemas import ProcessRequest, ProcessResponse, ProcessRequestPDF, AcceptedResponse, TaskRunBackQuestionsPayload, ProcessBackQuestionsEnqueueRequest
from src.services.processing import process_documents
from src.services.pdf_processing import process_pdf_documents

from src.clients.tasks_client import enqueue_http_json_task
from src.services.back_questions import process_back_questions_job
from src.settings import settings

router = APIRouter()

@router.post("/process", response_model=ProcessResponse)
async def process_endpoint(payload: ProcessRequest) -> ProcessResponse:
    try:
        data = process_documents(
            system_instructions_doc_id=payload.system_instructions_doc_id,
            base_prompt_doc_id=payload.base_prompt_doc_id,
            input_doc_id=payload.input_doc_id,
            output_doc_id=payload.output_doc_id,
            additional_params=payload.additional_params,
        )
        return ProcessResponse(**data)
    except HttpError as e:
        detail = getattr(e, "error_details", None) or str(e)
        raise HTTPException(status_code=403, detail=f"Google API error: {detail}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/process-pdf", response_model=ProcessResponse)
async def process_pdf_endpoint(payload: ProcessRequestPDF) -> ProcessResponse:
    try:
        data = process_pdf_documents(
            system_instructions_doc_id=payload.system_instructions_doc_id,
            base_prompt_doc_id=payload.base_prompt_doc_id,
            pdf_url=payload.pdf_url,
            output_doc_id=payload.output_doc_id,
            drive_file_id=payload.drive_file_id,
            additional_params=payload.additional_params,
        )
        return ProcessResponse(**data)
    except HttpError as e:
        status = getattr(e, "status_code", 500) or getattr(e.resp, "status", 500)
        detail = getattr(e, "error_details", None) or str(e)
        raise HTTPException(status_code=status, detail=f"Google API error: {detail}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/process-pdf-back-questions", response_model=AcceptedResponse, status_code=202)
def process_pdf_back_questions_enqueue(req: ProcessBackQuestionsEnqueueRequest, request: Request):
    # Derivar base URL si no viene por env y si el request tiene info
    #if not settings.tasks_handler_base_url:
        #base_url = str(request.base_url).rstrip("/")
        # WARNING: base_url por defecto apunta al dominio público entrante. Úsalo si procede en tu despliegue.
        # Si usas auth en Cloud Run, deberás setear TASKS_HANDLER_BASE_URL y TASKS_OIDC_AUDIENCE.
    payload = req.model_dump()
    task_name = enqueue_http_json_task(
        relative_path="/_tasks/process-pdf-back-questions-run",
        payload=payload,
        delay_seconds=0,
    )
    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content=AcceptedResponse(task_name=task_name).dict(),
    )


@router.post("/_tasks/process-pdf-back-questions-run")
def process_pdf_back_questions_run(req: TaskRunBackQuestionsPayload):
    res = process_back_questions_job(
        system_instructions_doc_id=req.system_instructions_doc_id,
        base_prompt_doc_id=req.base_prompt_doc_id,
        pdf_url=req.pdf_url,
        output_doc_id=req.output_doc_id,
        drive_file_id=req.drive_file_id,
        sampling_first_pages=req.sampling_first_pages or settings.backq_first_pages_default,
        sampling_last_pages=req.sampling_last_pages or settings.backq_last_pages_default,
        additional_params=req.additional_params or {},
    )
    return res