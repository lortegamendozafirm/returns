# tests/test_router_unit.py
from src.services.back_questions import _route_questions_to_chunks

def test_route_questions_simple():
    # 3 preguntas, 2 chunks de texto (simulados)
    questions = [
        {"id": "q1", "text": "¿Mencionó la coyote 'Flaca' alguna amenaza?"},
        {"id": "q2", "text": "¿Usaron armas durante los 10 días?"},
        {"id": "q3", "text": "¿Qué pasaba si alguien intentaba escapar?"},
    ]
    chunk_texts = [
        "La 'Flaca' dijo que habría consecuencias si no obedecían. Se escucharon amenazas.",
        "Durante los 10 días, había hombres armados vigilando. Intentos de escape eran castigados.",
    ]

    routing = _route_questions_to_chunks(
        questions=questions,
        chunk_texts=chunk_texts,
        k_top=2,       # cada pregunta sugiere hasta 2 chunks relevantes
        min_cover=1,   # cubrir al menos 1 chunk por pregunta
        chunk_cap=2    # tope de preguntas por chunk
    )

    # Debe haber al menos una asignación por pregunta total
    covered = set()
    for lst in routing.values():
        for q in lst:
            covered.add(q["id"])

    assert {"q1","q2","q3"}.issubset(covered), f"Preguntas sin cobertura: { {'q1','q2','q3'}-covered }"
