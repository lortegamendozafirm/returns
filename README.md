# Regresos API — Back Questions (PDF → Texto → Vertex → Google Docs + Google Sheets)

Servicio FastAPI para detectar y responder **“preguntas de regreso”** en documentos legales **PDF grandes**, con tracking de progreso en **Google Sheets**:

- **Descarga el PDF de Drive** (o usa `drive_file_id` directo).
- **Extrae texto localmente** (PyMuPDF → fallback PyPDF2) sin subir el PDF completo a Vertex/GCS.
- **Detecta preguntas** con modelo ligero (Flash) sobre **texto** de la **muestra P40 + U40**.
- **Rutea preguntas → chunks de texto** con un router heurístico (sin embeddings).
- **Responde** con estrategia:
  - **Híbrida (router + MAP/REDUCE por texto)**, o
  - **Per-question** (más lenta, pero más dirigida).
- **Escribe** las respuestas en un **Google Doc** con estilos nativos (H1/H2/listas).
- **(Nuevo)** Escribe **progreso** y **link del documento** en una **Google Sheet** si se pasa `sheet_id`, `row`, `col`.

> Cambios clave (modo texto + Sheets):
> - Eliminado el envío de PDFs por partes a Vertex AI (solo se envía TEXTO).
> - Detección y MAP/REDUCE trabajan sobre **texto extraído completo** (PyMuPDF / PyPDF2).
> - Nuevo router preguntas→chunks con límites `k_top_chunks`, `min_cover`, `chunk_cap`.
> - Fallback per-question cuando se fuerza `strategy="per_question"`.
> - Tracking de progreso en Google Sheets (`sheet_id`, `row`, `col`).
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
- [Progreso en Google Sheets](#progreso-en-google-sheets)
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
    C --> D[PDF → TEXTO\nPyMuPDF (blocks) / PyPDF2]
    D --> E["Sample P40+U40\nDetector (Flash)\nJSON: questions[]"]
    E -->|router| F[Chunks texto\n(PDF completo → chunks)]
    F --> G["MAP (Flash)\nrespuestas parciales por chunk"]
    G --> H["REDUCE (Pro)\nrespuesta final por pregunta"]
    H --> I["GDocs Client\nwrite_qas_native()"]
    I --> J[(Google Doc)]

    B --> K[Google Sheets\nProgreso (link + status)]
    K -.-> A
````

---

## Requisitos

* Python **3.11**
* Google Cloud Project con:

  * **Vertex AI** habilitado.
  * **Drive API / Docs API / Sheets API** habilitadas.
* Cuenta de servicio con permisos adecuados (ver [Permisos y scopes](#permisos-y-scopes)).
* (Recomendado) **PyMuPDF** (`fitz`) instalado para mejor extracción de texto; si no, se usa **PyPDF2** como fallback.

---

## Instalación

```bash
python -m venv venv
source venv/bin/activate           # (Windows) venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
```

Asegúrate de que `requirements.txt` incluya al menos:

```txt
fastapi
uvicorn
PyPDF2
pymupdf        # opcional pero recomendado
google-cloud-storage
google-api-python-client
google-auth
google-cloud-aiplatform
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

# --- Staging de PDFs (se usa poco en modo texto, pero conviene definirlo) ---
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

> **Nota:** Aunque el modo texto no sube el PDF completo a Vertex, se mantiene `PDF_STAGING_BUCKET` para otros pipelines y artefactos.

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

Procesa un PDF **grande** y escribe Q/A en un Google Doc, actualizando opcionalmente el progreso en una Google Sheet.

#### cURL (ejemplo)

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
    "sheet_id": "1Dyq4QJgwKcW3LEAetga43CkAdvzBZDtW7vLddPugVfo",
    "row": 5,
    "col": 3,
    "additional_params": {
      "visa_type": "visa t",
      "strategy": "hybrid",
      "detect_limit": 80,
      "k_top_chunks": 3,
      "min_cover": 2,
      "chunk_cap": 20,
      "throttle_s": 1.0,
      "base_prompt_ids": {
        "visa t": "1w64h4PmvmaHLImjVqT6R6be8kItQRyU5xBmB9YVoFZs",
        "default": "1t024Ow48Z605EHJgH47_eCYhP_cCFMXnt-jLpsmswOw"
      }
    }
  }'
```

#### Respuesta (200)

```json
{
  "status": "success",
  "message": "Q/A escritos en el documento (modo híbrido).",
  "output_doc_link": "https://docs.google.com/document/d/1XYZ.../edit"
}
```

> Para PDFs con **menos de 80 páginas**, el servicio delega a `process_pdf_documents` (pipeline anterior) para mantener compatibilidad.

---

## Cuerpos de petición

### `TaskRunBackQuestionsPayload` (JSON del endpoint)

Campos:

* `system_instructions_doc_id` (str)
  Doc con instrucciones de sistema / rol (prompt de sistema principal).

* `base_prompt_doc_id` (str|null)
  Doc con prompt base específico. Si es `null`, se resuelve dinámicamente vía:

  * `additional_params.base_prompt_ids[visa_type]`, o
  * `BASE_PROMPT_IDS_JSON` de settings (`default` como fallback).

* `pdf_url` (str)
  URL de Drive `https://drive.google.com/file/d/<ID>/view...`.
  (Para `gs://` necesitarías implementar descarga desde GCS; actualmente se levanta error si viene `gs://`.)

* `output_doc_id` (str)
  Doc destino para escribir Q/A.

* `drive_file_id` (str|null)
  Opcional, si ya conoces el `fileId` de Drive. Si no, se parsea desde `pdf_url`.

* `sampling_first_pages` / `sampling_last_pages` (int|null)
  Número de páginas que se usará para la **muestra** de detección de preguntas (P40/U40).
  Si son `null`, se usan los defaults de settings:

  * `BACKQ_FIRST_PAGES_DEFAULT`
  * `BACKQ_LAST_PAGES_DEFAULT`.

* `sheet_id` (str)
  ID de la **Google Sheet** donde se escribirá:

  * el **link** del `output_doc_id` en la celda `(row, col)`, y
  * el **status/progreso textual** en `(row, col+1)`.

* `row` (int, 1-based)
  Fila donde se escribirá link / status.

* `col` (int, 1-based)
  Columna donde se escribirá el **link**. El **status** va en `col+1`.

* `additional_params` (obj)
  Parámetros avanzados, por ejemplo:

  * `visa_type` (str)
    Clave de mapping para `BASE_PROMPT_IDS_JSON` o `base_prompt_ids`.

  * `base_prompt_ids` (obj)
    Override ad-hoc de prompts base, por ejemplo:
    `{ "visa t": "<docId>", "visa u": "<docId>", "default": "<docId>" }`.

  * `strategy` (`"hybrid"` | `"per_question"`)

    * `"hybrid"`: router → MAP por chunk → REDUCE por pregunta (recomendado).
    * `"per_question"`: pipeline por pregunta, usando solo los Top-K chunks relevantes.

  * Parámetros de ruteo / control:

    * `detect_limit` (int)
    * `k_top_chunks` (int)
    * `min_cover` (int)
    * `chunk_cap` (int)
    * `throttle_s` (float)

---

## Parámetros de control

### Detección (texto de muestra)

* `sampling_first_pages` / `sampling_last_pages`

  * Por defecto 40 / 40.
  * Se extrae un PDF **reducido** (primeras N + últimas M páginas) y luego se extrae el **texto completo** de ese sample.
* `BACKQ_DETECT_LIMIT` (env: `BACKQ_DETECT_LIMIT`)

  * Máximo número de preguntas que el detector puede devolver.
* Detector:

  * Prompt en `_detect_back_questions_via_model_text` (modelo Flash).
  * Fallback `_detect_back_questions_regex` sólo si el detector ML no devuelve nada.

### Chunking (PDF completo)

* `PDF_MAX_PAGES_PER_CHUNK` (env)

  * Tamaño objetivo de páginas por chunk.
  * El código usa `max(5, PDF_MAX_PAGES_PER_CHUNK)`.

### Enrutamiento preguntas → chunks (`_route_questions_to_chunks`)

* `BACKQ_K_TOP_CHUNKS` (`k_top_chunks`)

  * Número de chunks relevantes por pregunta (heurística por tokens).

* `BACKQ_MIN_COVER` (`min_cover`)

  * Cobertura mínima: número de chunks distintos en los que debe aparecer cada pregunta.

* `BACKQ_CHUNK_CAP` (`chunk_cap`)

  * Máximo de preguntas por chunk. Si se excede:

    * Se **priorizan** preguntas para cada chunk.
    * El resto se derrama a otros chunks, respetando orden de relevancia.
    * Si aún queda overflow, se envía al último chunk.

* `BACKQ_THROTTLE_S` (`throttle_s`)

  * Espera en segundos entre llamadas MAP/por pregunta para evitar `429`.

### Estrategias

* **Híbrida (`strategy != "per_question"`)**:

  * Detección → routing → MAP JSON por chunk → REDUCE por pregunta.
  * Fallback dirigido para preguntas sin evidencia (Top-2 chunks).

* **Per-question (`strategy = "per_question"`)**:

  * Para cada pregunta, se seleccionan los Top-K chunks de texto.
  * Se hace un mini-MAP/REDUCE por pregunta.

---

## Progreso en Google Sheets

El tracking en Sheets se implementa via `_make_sheet_updater`:

* Si se provee `sheet_id`, `row`, `col`:

  * `link` se escribe en la celda **(row, col)**.
  * `status` se escribe en **(row, col+1)**.
* La columna se convierte a letra con `_col_to_letter()`.

Durante el job se actualizan mensajes de status aproximados, por ejemplo:

* `"10% Inicio"`
* `"20% Prompts listos"`
* `"30% PDF descargado"`
* `"40% Muestra procesada"`
* `"50% X preguntas detectadas"`
* `"60% Ruteo de preguntas listo"`
* Progreso incremental durante MAP/REDUCE (`"65% MAP 1/4"`, etc.)
* `"90% REDUCE por pregunta"`
* `"95% Escribiendo Doc"`
* `"100% ✔️"` o `"100% ✔️ (sin preguntas detectadas)"`

> Si `sheet_id`, `row` o `col` no se pasan o vienen vacíos, el helper simplemente **no escribe nada** y el job continúa normal.

---

## Permisos y scopes

La cuenta de servicio debe tener:

* **Vertex AI User** (o rol equivalente para invocar modelos generativos).
* **Drive**:

  * Lectura de archivos PDF.
* **Docs**:

  * Edición del documento de salida (`output_doc_id`).
* **Sheets**:

  * Escritura de progreso (link + status) en la Google Sheet.

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

  * Inicio / fin de job.
  * Tamaño del PDF, número de páginas.
  * Patrón de encabezado detectado (`_first_heading_variant_hit`).
  * Preguntas detectadas (`_log_detected_questions`).
  * Número de chunks y cobertura por pregunta (`🧭 Q[...] cubierta en chunks`).
  * Errores de `ResourceExhausted` / `429` y estrategias de degradación.
  * Fallbacks activados (regex, per-question, dirigido Top-2).

---

## Rendimiento y costos

* **Modo texto** reduce:

  * I/O de subida de PDFs a Vertex.
  * Tokenización innecesaria de páginas irrelevantes (se trabajan sólo los chunks más relevantes).
* Control de llamadas mediante:

  * `detect_limit`, `k_top_chunks`, `min_cover`, `chunk_cap`, `throttle_s`.
* **Estrategia híbrida**:

  * Más eficiente al agrupar preguntas por chunk de texto.
* **Estrategia per-question**:

  * Más costosa en tokens/llamadas, pero más dirigida cuando:

    * Hay pocas preguntas, o
    * Las preguntas están muy dispersas.

---

## Limitaciones conocidas

* **PyMuPDF / PyPDF2**:

  * Funcionan mejor con PDFs **born-digital**.
  * Si el PDF está **escaneado**, con imágenes o capas extrañas, la extracción de texto puede ser pobre o vacía.

  *Mitigación:* Ejecutar un pipeline de OCR (Cloud Vision, Document AI, Tesseract, etc.) antes de este servicio.

* El **formato** visual (paginación exacta, tablas, etc.) se pierde al convertir a texto; los `page_hint` son heurísticos cuando los da el detector.

* El SDK `vertexai.generative_models` puede mostrar **deprecation warnings** en algunas versiones.
  Se recomienda tener plan de migración a las APIs GenAI más recientes de Vertex AI.

---

## Solución de problemas

* **403/404 al leer Drive/Docs**

  * Verifica que el archivo/Doc esté **compartido con la SA**.
  * Revisa que el `fileId`/`docId` sea correcto.

* **`ValueError: base_prompt_doc_id` no resuelto**

  * Asegúrate de:

    * Pasar `base_prompt_doc_id`, o
    * Configurar `additional_params.base_prompt_ids` con la clave de `visa_type`, o
    * Tener `BASE_PROMPT_IDS_JSON` en settings con la clave `visa_type` o `default`.

* **`ResourceExhausted` / `429` en MAP o per-question**

  * El código hace reintentos con subsets reducidos y throttle:

    * Baja `detect_limit`, `k_top_chunks`, `chunk_cap`.
    * Aumenta `throttle_s`.

* **Texto vacío**

  * Revisa que el PDF no sea sólo imágenes.
  * Si lo es, agrega un paso de OCR previo.

* **Sin preguntas detectadas**

  * Se registrará:

    * `DET-ML: 0 preguntas`
    * Intento de fallback `DET-REGEX`.
  * Si aun así no hay preguntas:

    * Se escribe un doc de salida vacío con título `"Respuestas"`.
    * Se regresa mensaje `"No se detectaron preguntas regreso en el documento."`
    * Status en Sheet se marca como `"100% ✔️ (sin preguntas detectadas)"`.

---

## Estructura del repo

```text
src/
  api/
    routes.py                 # Endpoint FastAPI (_tasks/process-pdf-back-questions-run)
  clients/
    drive_client.py           # Drive helpers (assert, parse, download_file_bytes)
    gdocs_client.py           # Docs helpers (lectura/escritura nativa de Q/A)
    gcs_client.py             # (opcional) staging/artefactos
    sheets_client.py          # Helper para escribir progreso en Google Sheets
    vertex_client.py          # Llamadas a Vertex AI (Flash/Pro) con retries
  domain/
    schemas.py                # Pydantic schemas (TaskRunBackQuestionsPayload, etc.)
  services/
    pdf_processing.py         # Pipeline genérico previo (<80 páginas)
    back_questions.py         # Pipeline Back Questions (modo texto + router + Sheets)
  utils/
    logger.py                 # Logger JSON/local
  auth.py                     # Credenciales + init Vertex
  main.py                     # FastAPI app + router
Dockerfile
requirements.txt
```

---

## Licencia

Privado / Uso interno TMLF.
