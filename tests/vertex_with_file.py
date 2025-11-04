from src.clients.vertex_client import generate_text_with_files
from src.utils.logger import get_logger

log = get_logger(__name__)

if __name__ == "__main__":
    prompt = "Resume el PDF adjunto en 3 bullets claros."
    uri = "gs://my-bucket-out/uploads/test.pdf"   # <-- ajusta
    out = generate_text_with_files(prompt, [uri])
    log.info(f"✅ Vertex with file OK | len={len(out)}")
    print(out[:500])
