"""
Parte C del pipeline: consecucion del PDF completo.

Trae un lote de papers recientes (Parte A), filtra por relevancia (Parte B) y,
para el top pick (o para todos, con --all), intenta conseguir el PDF completo.

Uso:
    OPENALEX_MAILTO=tu@email.com ANTHROPIC_API_KEY=sk-ant-... \\
        python scripts/resolve_pdf_test.py [--all]
"""

import os
import sys
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from openalex.client import OpenAlexError, fetch_papers  # noqa: E402
from openalex.journals import source_id_filter  # noqa: E402
from pdf.client import resolve_pdf  # noqa: E402
from relevance.client import RelevanceError, evaluate_papers  # noqa: E402

YEARS_BACK = 10
N_CANDIDATES = 20
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", ".pdf_downloads")


def main() -> None:
    mailto = os.environ.get("OPENALEX_MAILTO")
    if not mailto:
        sys.exit("Falta OPENALEX_MAILTO en el entorno.")

    from_year = date.today().year - YEARS_BACK

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
        sys.exit("Ningun paper con abstract disponible.")

    try:
        assessment = evaluate_papers(papers)
    except RelevanceError as e:
        sys.exit(f"Error evaluando relevancia: {e}")

    targets = (
        papers
        if "--all" in sys.argv
        else ([papers[assessment.top_pick_index]] if assessment.top_pick_index is not None else [])
    )
    if not targets:
        sys.exit("No hay top pick en esta corrida; corre con --all para probar sobre todos los candidatos.")

    for p in targets:
        print(f"--- {p.title} ({p.journal}, {p.publication_year}) ---")
        result = resolve_pdf(p, out_dir=OUT_DIR, unpaywall_email=mailto)
        print(f"  Fuente:   {result.source or '(ninguna)'}")
        print(f"  Version:  {result.version or '(ninguna)'}")
        print(f"  URL:      {result.url or '(ninguna)'}")
        print(f"  Archivo:  {result.local_path or '(no descargado)'}")
        if result.notes:
            print(f"  Notas:    {result.notes}")
        print()


if __name__ == "__main__":
    main()
