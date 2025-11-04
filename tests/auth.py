from src.auth import get_all_clients
from src.clients.gdocs_client import get_document_content, write_to_document
from src.clients.vertex_client import generate_text

# Inicializar clientes
clients = get_all_clients()
print("Clientes inicializados:", clients.keys())

# Leer un documento de prueba
doc_text = get_document_content("1U4zwjrEytz6HVDS8gRjydk3x9EoWS0eb7M8HM4EYLfs")
print(doc_text[:200])

# Generar texto con Gemini
output = generate_text("Resume este texto brevemente:\n" + doc_text[:1000])

# Escribir resultado
write_to_document("1U4zwjrEytz6HVDS8gRjydk3x9EoWS0eb7M8HM4EYLfs", output)

