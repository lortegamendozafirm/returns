# Manual de Primeros Pasos: API de Procesamiento de Documentos (Configuración Local)

Este manual describe los pasos para configurar el entorno local del proyecto ai-doc-processor y dejarlo listo para su despliegue en Google Cloud Run.

## Sección 1: Prerrequisitos

Antes de comenzar, asegúrate de tener lo siguiente:

Cuenta de Google Cloud: Un proyecto activo con la facturación habilitada.
Google Cloud SDK: Instalado y autenticado en tu máquina (gcloud auth login).
Python 3.9+ y pip.
Una Service Account (SA): Creada en tu proyecto de GCP. Anota su email.
Permisos de la SA: La SA debe tener el rol Vertex AI User (roles/aiplatform.user).
Carpeta y Documentos en Google Drive:
Una carpeta en Google Drive.
Comparte esa carpeta con el email de tu SA dándole permisos de Editor.
Dentro de la carpeta, crea los 4 Google Docs necesarios y anota sus IDs.
Sección 2: Estructura y Configuración del Proyecto
Crear la Estructura de Carpetas:
Organiza tu proyecto con la siguiente estructura modular:

ai-doc-processor/
├── src/
│   ├── api/
│   ├── domain/
│   ├── services/
│   ├── clients/
│   ├── utils/
│   ├── settings.py
│   └── main.py
├── .env
└── requirements.txt
Definir las Dependencias (requirements.txt):
Crea el archivo requirements.txt con las librerías necesarias:

fastapi
uvicorn[standard]
pydantic
python-dotenv
google-cloud-aiplatform
google-api-python-client
google-auth-httplib2
google-auth-oauthlib
Configurar las Variables de Entorno (.env):
Crea el archivo .env para la configuración local. Este archivo no debe subirse a tu repositorio de código.

# .env
GCP_PROJECT_ID="tu-project-id-de-gcp"
GCP_REGION="us-central1"
LOG_LEVEL="INFO"
Sección 3: Ejecución y Prueba Local
Instalar Dependencias:
Desde la raíz del proyecto, ejecuta:

pip install -r requirements.txt
Autenticación Local:
Para que tu entorno local pueda usar las APIs de Google, autentica tu SDK como usuario final.

gcloud auth application-default login
Iniciar el Servidor:
Desde la raíz del proyecto, ejecuta:

uvicorn src.main:app --reload
La API estará disponible en http://127.0.0.1:8000.

Ejemplo de Payload para Pruebas:
Para probar el endpoint /process, puedes usar una herramienta como curl con un payload JSON como el siguiente:

{
  "system_instructions_doc_id": "ID_DEL_DOC_DE_INSTRUCCIONES",
  "base_prompt_doc_id": "ID_DEL_DOC_DE_PROMPT_BASE",
  "input_doc_id": "ID_DEL_DOC_DE_ENTRADA",
  "output_doc_id": "ID_DEL_DOC_DE_SALIDA",
  "additional_params": {
    "variable1": "valor_dinamico"
  }
}
Una respuesta exitosa devolverá un JSON con el estado y el enlace al documento de salida.

Con estos pasos, la aplicación está configurada y probada localmente, lista para ser empaquetada y desplegada.