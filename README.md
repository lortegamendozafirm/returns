# Regresos API — Back Questions (PDF → Texto → Vertex → Google Docs)

Servicio FastAPI para detectar y responder **“preguntas de regreso”** en documentos legales **PDF grandes**:
- **Descarga el PDF de Drive** (o `drive_file_id` directo).
- **Extrae texto localmente** (PyPDF2) sin subir el PDF completo a GCS.
- **Detecta preguntas** con modelo ligero (Flash) sobre **texto** del **muestra P40 + U40**.
- **Responde** con estrategia **híbrida (router + MAP/REDUCE por texto)** o **per_question**.
- **Escribe** las respuestas en un **Google Doc** con estilos nativos (H1/H2/listas).

> Cambios clave (modo texto):
> - Eliminado el envío de PDFs por partes a Vertex AI.
> - Detección y MAP/REDUCE trabajan sobre **texto extraído** por PyPDF2.
> - Mantiene compat `<80 páginas` llamando a `src.services.pdf_processing.process_pdf_documents`.

---

## Tabla de contenidos

- [Arquitectura](#arquitectura)
- [Requisitos](#requisitos)
- [Instalación](#instalación)
- [Configuración (.env)](#configuración-env)
- [Ejecución local](#ejecución-local)
- [Despliegue en Cloud Run](#despliegue-en-cloud-run)
- [Endpoints](#endpoints)
- [Cuerpos de petición](#cuerpos-de-petición)
- [Parámetros de control](#parámetros-de-control)
- [Permisos y scopes](#permisos-y-scopes)
- [Registro y monitoreo](#registro-y-monitoreo)
- [Rendimiento y costos](#rendimiento-y-costos)
- [Limitaciones conocidas](#limitaciones-conocidas)
- [Solución de problemas](#solución-de-problemas)
- [Estructura del repo](#estructura-del-repo)
- [Licencia](#licencia)

---

## Arquitectura

```mermaid
flowchart LR
    A[Cliente] -->|POST JSON| B[FastAPI\n/_tasks/process-pdf-back-questions-run]
    B --> C[Drive Client\nassert & download]
    C --> D[PyPDF2\nMuestra P40+U40 → Texto]
    D --> E["Detector (Flash)\nJSON: questions[]"]
    E -->|router| F[Chunks de texto]
    F --> G["MAP (Flash)\nrespuestas parciales por chunk"]
    G --> H["REDUCE (Pro)\nrespuesta final por pregunta"]
    H --> I["GDocs Client\nwrite_qas_native()"]
    I --> J[(Google Doc)]
````

---

## Requisitos

* Python **3.11**
* Google Cloud Project con:

  * **Vertex AI** habilitado.
  * **Drive API / Docs API / Sheets API** habilitadas.
* Cuenta de servicio con permisos adecuados (ver [Permisos y scopes](#permisos-y-scopes)).

---

## Instalación

```bash
python -m venv venv
source venv/bin/activate           # (Windows) venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
```

---

## Configuración (.env)

Usa el ejemplo y ajusta IDs reales:

```env
# --- Identidad del proyecto ---
GCP_PROJECT_ID=ortega-473114
GCP_LOCATION=us-central1

# --- Cuenta de servicio ---
SA_EMAIL=gctest@ortega-473114.iam.gserviceaccount.com
GOOGLE_APPLICATION_CREDENTIALS=sa_key.json
DWD_SUBJECT=jvargasmendozafirm@gmail.com

# --- Google Drive / Workspace ---
SHARED_FOLDER_ID=16zkZfYKitE0_xcpY_EnYpa5r5VQDLyDh
EXISTING_DOC_ID=1U4zwjrEytz6HVDS8gRjydk3x9EoWS0eb7M8HM4EYLfs
EXISTING_SHEET_ID=1x1s-KJYrcKluifYEjnh2FR1eF7CjUjnnow3XWAAaWUo
DOC_NAME=Plantilla Testimonio
SHEET_NAME=Registro Artefactos

# --- Logging / Región / Modo ---
LOG_LEVEL=INFO
ENVIRONMENT=local

# --- Staging de PDFs ---
PDF_STAGING_BUCKET=my-bucket-out
PDF_MAX_PAGES_PER_CHUNK=60
PDF_USE_FILE_API=true

# --- Vertex AI ---
VERTEX_MODEL_ID=gemini-2.5-flash
VERTEX_MODEL_ID_PRO=gemini-2.5-pro

# --- Modelos MAP/REDUCE ---
MAP_MODEL_ID=gemini-2.5-flash
REDUCE_MODEL_ID=gemini-2.5-pro

# --- Back Questions / routing ---
BACKQ_FIRST_PAGES_DEFAULT=40
BACKQ_LAST_PAGES_DEFAULT=40
BACKQ_DETECT_LIMIT=100
BACKQ_STRATEGY=hybrid
BACKQ_K_TOP_CHUNKS=3
BACKQ_MIN_COVER=2
BACKQ_CHUNK_CAP=20
BACKQ_THROTTLE_S=1.0

# --- Base prompts por tipo de visa ---
BASE_PROMPT_IDS_JSON={"vawa":"19Y-lXARg1xkmRmwG7RsHUSA73PKnfaU2nfFIkYcI9Q8","visa t":"1w64h4PmvmaHLImjVqT6R6be8kItQRyU5xBmB9YVoFZs","visa u":"1t024Ow48Z605EHJgH47_eCYhP_cCFMXnt-jLpsmswOw","default":"1t024Ow48Z605EHJgH47_eCYhP_cCFMXnt-jLpsmswOw"}
```

> **Nota:** Aunque el modo texto no sube el PDF completo, se sigue usando `PDF_STAGING_BUCKET` para logs/artefactos eventuales (p.ej., muestras). Puedes dejarlo configurado.

---

## Ejecución local

```bash
uvicorn src.main:app --host 0.0.0.0 --port 8080 --reload
```

---

## Despliegue en Cloud Run

```bash
gcloud auth login
gcloud config set project $GCP_PROJECT_ID

gcloud builds submit --tag gcr.io/$GCP_PROJECT_ID/regresos-api
gcloud run deploy regresos-api \
  --image gcr.io/$GCP_PROJECT_ID/regresos-api \
  --region $GCP_LOCATION \
  --platform managed \
  --allow-unauthenticated \
  --set-env-vars GCP_PROJECT_ID=$GCP_PROJECT_ID,GCP_LOCATION=$GCP_LOCATION,ENVIRONMENT=prod,LOG_LEVEL=INFO,PDF_STAGING_BUCKET=my-bucket-out,MAP_MODEL_ID=gemini-2.5-flash,REDUCE_MODEL_ID=gemini-2.5-pro
```

> Si usas **autenticación** con OIDC, restringe `--allow-unauthenticated` y agrega políticas IAM/ID Tokens en tu cliente.

---

## Endpoints

### `POST /_tasks/process-pdf-back-questions-run`

Procesa un PDF y escribe Q/A en un Google Doc.

**cURL**

```bash
curl -X POST "http://localhost:8080/_tasks/process-pdf-back-questions-run" \
  -H "Content-Type: application/json" \
  -d '{
    "system_instructions_doc_id": "1abc...sys",
    "base_prompt_doc_id": null,
    "pdf_url": "https://drive.google.com/file/d/1DEF.../view",
    "output_doc_id": "1XYZ...out",
    "drive_file_id": null,
    "sampling_first_pages": 40,
    "sampling_last_pages": 40,
    "additional_params": {
      "visa_type": "visa t",
      "strategy": "hybrid",
      "detect_limit": 80,
      "k_top_chunks": 3,
      "min_cover": 2,
      "chunk_cap": 20,
      "throttle_s": 1.0
    }
  }'
```

**Respuesta (200):**

```json
{
  "status": "success",
  "message": "Q/A escritos en el documento (modo híbrido).",
  "output_doc_link": "https://docs.google.com/document/d/1XYZ.../edit"
}
```

---

## Cuerpos de petición

* `system_instructions_doc_id` (str): Doc con instrucciones de sistema.
* `base_prompt_doc_id` (str|null): Doc con prompt base. Si `null`, se resuelve vía `BASE_PROMPT_IDS_JSON` + `additional_params.visa_type` o el `default`.
* `pdf_url` (str): URL de Drive `https://drive.google.com/file/d/<ID>/view...`. (Para `gs://` se requeriría implementación de descarga GCS).
* `output_doc_id` (str): Doc destino para escribir Q/A.
* `drive_file_id` (str|null): Opcional, si ya conoces el fileId de Drive.
* `sampling_first_pages` / `sampling_last_pages` (int): Tamaño de muestra para detección.
* `additional_params` (obj):

  * `visa_type` (str): clave de mapping para `BASE_PROMPT_IDS_JSON`.
  * `base_prompt_ids` (obj): override ad-hoc `{ "visa t": "<docId>", "default": "<docId>" }`.
  * `strategy` (`"hybrid"` | `"per_question"`).
  * Parámetros de ruteo: `detect_limit`, `k_top_chunks`, `min_cover`, `chunk_cap`, `throttle_s`.

---

## Parámetros de control

* **Detección (texto de muestra)**:

  * `sampling_first_pages` / `sampling_last_pages`: por defecto 40/40.
  * `BACKQ_DETECT_LIMIT`: máximo de preguntas detectadas.

* **Híbrido (router + MAP/REDUCE por texto)**:

  * `BACKQ_K_TOP_CHUNKS` (default 3).
  * `BACKQ_MIN_COVER` (default 2).
  * `BACKQ_CHUNK_CAP` (default 20).
  * `BACKQ_THROTTLE_S` (default 1.0s entre llamados MAP).

* **Fallback `per_question`**:

  * Top-K chunks de texto por pregunta (default 3).

---

## Permisos y scopes

La cuenta de servicio debe tener:

* **Vertex AI User** (o invocación de modelos generativos).
* **Drive** (lectura de archivos PDF).
* **Docs** (edición del documento de salida).
* (Opcional) **Sheets** si usas funciones auxiliares.

Scopes usados (construidos en `src/auth.py`):

* `https://www.googleapis.com/auth/cloud-platform`
* `https://www.googleapis.com/auth/drive.readonly`
* `https://www.googleapis.com/auth/documents`
* `https://www.googleapis.com/auth/spreadsheets`

---

## Registro y monitoreo

* Logs estructurados (JSON) en Cloud Run cuando `ENVIRONMENT != local`.
* En local, logs legibles con timestamps.
* Mensajes clave:

  * Inicio de job, tamaño del PDF, cobertura por pregunta, MAP/REDUCE, fallbacks.

---

## Rendimiento y costos

* **Modo texto** reduce I/O y costos de subida/descarga de PDFs grandes a Vertex.
* Controla el volumen de llamadas con:

  * `detect_limit`, `k_top_chunks`, `chunk_cap`, `throttle_s`.
* **`per_question`** puede disparar más tokens/llamadas; usarlo para precisión o documentos con preguntas muy dispersas.

---

## Limitaciones conocidas

* **PyPDF2** extrae texto de PDFs **born-digital**. Si el PDF está **escaneado** o tiene capas/etiquetas complejas, el texto puede ser incompleto.

  * *Mitigación:* Pre-OCR (p.ej., Cloud Vision OCR, Tesseract) previo a este pipeline.
* **Formato** y **paginación** se pierden al extraer texto; los “page_hint” son heurísticos si vienen del detector.
* El SDK `vertexai.generative_models` muestra **deprecation warning** (aviso de Google); se recomienda planear migración a las **APIs nuevas** de Vertex AI GenAI cuando corresponda.

---

## Solución de problemas

* **403/404 al leer Drive/Docs**: verifica *compartir con la SA* y que el `fileId`/`docId` sea correcto.
* **`ValueError: base_prompt_doc_id` no resuelto**: define `base_prompt_doc_id`, o `BASE_PROMPT_IDS_JSON` con clave `visa_type` o `default`.
* **`ResourceExhausted` en REDUCE**: el cliente ya reintenta exponencialmente; baja `detect_limit`, `k_top_chunks`, o aumenta `throttle_s`.
* **Texto vacío**: confirma que el PDF no es escaneado; si lo es, agrega OCR.

---

## Estructura del repo

```
src/
  api/
    routes.py                 # Endpoint FastAPI
  clients/
    drive_client.py           # Drive helpers
    gdocs_client.py           # Docs helpers (lectura/escritura nativa)
    gcs_client.py             # (opcional) staging/artefactos
    vertex_client.py          # Llamadas a Vertex AI (con retries)
  domain/
    schemas.py                # Pydantic schemas
  services/
    pdf_processing.py         # Pipeline genérico (batch por PDF o MR)
    back_questions.py         # *** Pipeline Back Questions (modo texto) ***
  utils/
    logger.py                 # Logger JSON/local
  auth.py                     # Credenciales + init Vertex
  main.py                     # FastAPI app
Dockerfile
requirements.txt
```

---

## Licencia

Privado / Uso interno TMLF.

```
```
