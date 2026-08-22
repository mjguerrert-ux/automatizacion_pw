"""
Parte D del pipeline: generacion de la ficha estructurada en espanol.

Encadena todo el pipeline hasta ahora: trae candidatos (A), filtra por
relevancia (B), consigue el PDF del top pick (C), y genera + imprime la
ficha final (D), lista para lo que sera el mensaje de WhatsApp (E).

Uso:
    OPENALEX_MAILTO=tu@email.com ANTHROPIC_API_KEY=sk-ant-... \\
        python scripts/generate_ficha_test.py
"""

import os
import sys
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from ficha.client import FichaError, format_ficha_message, generate_ficha  # noqa: E402
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

    print("A. Trayendo candidatos de OpenAlex...")
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

    print(f"   {len(papers)} candidatos con abstract.\n")

    print("B. Evaluando relevancia + importancia...")
    try:
        assessment = evaluate_papers(papers)
    except RelevanceError as e:
        sys.exit(f"Error evaluando relevancia: {e}")

    if assessment.top_pick_index is None:
        sys.exit("Ningun paper fue suficientemente relevante/importante en esta corrida.")

    top = papers[assessment.top_pick_index]
    print(f"   Top pick: {top.title}")
    print(f"   Razon: {assessment.top_pick_reasoning}\n")

    print("C. Consiguiendo el PDF...")
    pdf_result = resolve_pdf(top, out_dir=OUT_DIR, unpaywall_email=mailto)
    print(f"   Fuente: {pdf_result.source} | version: {pdf_result.version}")
    if not pdf_result.local_path:
        sys.exit(f"No se pudo descargar el PDF ({pdf_result.notes}); no se puede generar la ficha (D).")
    print(f"   Archivo: {pdf_result.local_path}\n")

    print("D. Generando la ficha (leyendo el PDF completo)...")
    try:
        ficha = generate_ficha(top, pdf_result.local_path)
    except FichaError as e:
        sys.exit(f"Error generando la ficha: {e}")

    print("\n" + "=" * 60)
    print(format_ficha_message(ficha, top))
    print("=" * 60)


if __name__ == "__main__":
    main()
