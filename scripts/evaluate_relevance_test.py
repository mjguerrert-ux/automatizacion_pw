"""
Parte B del pipeline: filtro de relevancia + importancia con la API de Claude.

Trae un lote de papers recientes del top 40 de revistas (Parte A, ordenados por
fecha de publicacion para simular "abstracts nuevos") y los pasa por el filtro
de relevancia. Todavia no resuelve PDF (Parte C) ni redacta la ficha (Parte D).

Uso:
    OPENALEX_MAILTO=tu@email.com ANTHROPIC_API_KEY=sk-ant-... \\
        python scripts/evaluate_relevance_test.py
"""

import os
import sys
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from openalex.client import OpenAlexError, fetch_papers  # noqa: E402
from openalex.journals import source_id_filter  # noqa: E402
from relevance.client import RelevanceError, evaluate_papers  # noqa: E402

YEARS_BACK = 10
N_CANDIDATES = 20


def main() -> None:
    from_year = date.today().year - YEARS_BACK

    print(f"Trayendo {N_CANDIDATES} papers recientes (ordenados por fecha) como candidatos...\n")
    try:
        papers = fetch_papers(
            source_ids=source_id_filter(),
            from_year=from_year,
            limit=N_CANDIDATES,
            sort="publication_date:desc",
        )
    except OpenAlexError as e:
        sys.exit(f"Error consultando OpenAlex: {e}")

    papers = [p for p in papers if p.abstract]
    if not papers:
        sys.exit("Ninguno de los papers traidos tiene abstract disponible; no hay nada que evaluar.")

    print(f"{len(papers)} papers con abstract disponible. Evaluando relevancia con Claude...\n")

    try:
        assessment = evaluate_papers(papers)
    except RelevanceError as e:
        sys.exit(f"Error evaluando relevancia: {e}")

    for ev in assessment.evaluations:
        p = papers[ev.paper_index]
        marker = "PICK" if ev.paper_index == assessment.top_pick_index else "    "
        relevance = "relevante" if ev.is_relevant else "no relevante"
        themes = ", ".join(ev.themes) or "(ninguno)"
        print(f"[{marker}] #{ev.paper_index} score={ev.importance_score:>2} {relevance:12} temas=({themes})")
        print(f"       {p.title}")
        print(f"       {p.journal} ({p.publication_year})")
        print(f"       Razon: {ev.reasoning}")
        print()

    print("=== Top pick ===")
    if assessment.top_pick_index is None:
        print("Ningun paper fue suficientemente relevante/importante en esta corrida.")
    else:
        p = papers[assessment.top_pick_index]
        print(f"{p.title}")
        print(f"{p.journal} ({p.publication_year})")
        print(f"DOI: {p.doi}")
        print(f"Razon: {assessment.top_pick_reasoning}")


if __name__ == "__main__":
    main()
