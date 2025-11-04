from src.clients.vertex_client import generate_text
from src.utils.logger import get_logger

log = get_logger(__name__)

if __name__ == "__main__":
    out = generate_text("Dime 'pong' en una sola palabra.")
    log.info(f"✅ Vertex text OK | len={len(out)} | out={out[:80]!r}")
    print(out)
