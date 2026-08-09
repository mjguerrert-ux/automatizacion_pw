"""
Parte A del pipeline: conectar con OpenAlex y traer papers de prueba del
top 40 de revistas de economia, publicados en los ultimos 10 anios.

No filtra todavia por tema (poblacion juvenil, genero, salud, educacion,
inferencia causal) ni por relevancia: eso es la Parte B (filtro con la API
de Claude). Aqui solo se valida que la conexion y el filtrado por
revista + fecha funcionan.

Uso:
    OPENALEX_MAILTO=tu@email.com python scripts/fetch_test_papers.py
"""

import os
import sys
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from openalex.client import OpenAlexError, fetch_papers  # noqa: E402
from openalex.journals import TOP_40_ECON_JOURNALS, source_id_filter  # noqa: E402

YEARS_BACK = 10
N_TEST_PAPERS = 5


def main() -> None:
    from_year = date.today().year - YEARS_BACK

    print(f"Revistas consideradas: {len(TOP_40_ECON_JOURNALS)} (top 40 por 2yr_mean_citedness)")
    print(f"Rango de fechas: {from_year}-01-01 a hoy")
    print(f"Trayendo {N_TEST_PAPERS} papers de prueba, ordenados por cited_by_count desc...\n")

    try:
        papers = fetch_papers(
            source_ids=source_id_filter(),
            from_year=from_year,
            limit=N_TEST_PAPERS,
        )
    except OpenAlexError as e:
        sys.exit(f"Error consultando OpenAlex: {e}")

    if not papers:
        sys.exit("No se encontraron papers. Revisa el filtro de revistas/fechas.")

    for i, p in enumerate(papers, start=1):
        authors = ", ".join(p.authors[:6]) + (" et al." if len(p.authors) > 6 else "")
        abstract_preview = (p.abstract or "(sin abstract)")[:280]
        pdf_status = p.oa_pdf_url or ("OA sin pdf_url directo" if p.is_oa else "sin acceso abierto")

        print(f"--- Paper {i}/{len(papers)} ---")
        print(f"Titulo:        {p.title}")
        print(f"Revista:       {p.journal} ({p.publication_year})")
        print(f"Autores:       {authors or '(sin autores listados)'}")
        print(f"Citas:         {p.cited_by_count}")
        print(f"DOI:           {p.doi or '(sin DOI)'}")
        print(f"PDF / OA:      {pdf_status}")
        print(f"Landing page:  {p.landing_page_url or '(no disponible)'}")
        print(f"Abstract:      {abstract_preview}{'...' if p.abstract and len(p.abstract) > 280 else ''}")
        print()


if __name__ == "__main__":
    main()
