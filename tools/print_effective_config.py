# tools/print_effective_config.py
from src.settings import settings

def mask(v: str, keep=6):
    if not v or len(v) <= keep: return v
    return v[:keep] + "…"

def main():
    print("== Effective Settings ==")
    print("project:", settings.gcp_project_id)
    print("location:", settings.gcp_location)
    print("env:", settings.environment)
    print("bucket:", settings.pdf_staging_bucket)
    print("pdf_max_pages_per_chunk:", settings.pdf_max_pages_per_chunk)
    print("models: map =", settings.map_model_id, "| reduce =", settings.reduce_model_id)
    print("strategy:", settings.backq_strategy)
    print("router: k_top =", settings.backq_k_top_chunks,
          "min_cover =", settings.backq_min_cover, "chunk_cap =", settings.backq_chunk_cap)
    mp = settings.base_prompt_ids()
    print("base_prompt_ids:", {k: mask(v) for k, v in mp.items()})

if __name__ == "__main__":
    main()
