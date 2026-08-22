"""
Corrida real del pipeline de papers: trae candidatos (A), filtra por
relevancia + importancia (B), consigue el PDF del top pick (C), genera la
ficha (D) y la MANDA por Telegram — texto de la ficha + el PDF adjunto.

Usa un bot de Telegram separado del pipeline de oportunidades (variables
TELEGRAM_BOT_TOKEN_PAPERS / TELEGRAM_CHAT_ID_PAPERS), porque son dos chats
distintos que no deben mezclarse.

Solo marca el paper como "enviado" (para no repetirlo en la siguiente
corrida) despues de que el envio por Telegram fue exitoso.

Uso:
    OPENALEX_MAILTO=tu@email.com ANTHROPIC_API_KEY=sk-ant-... \\
        TELEGRAM_BOT_TOKEN_PAPERS=123456789:ABC-... TELEGRAM_CHAT_ID_PAPERS=... \\
        python scripts/send_papers.py
"""

import os
import sys
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from ficha.client import FichaError, format_ficha_message, generate_ficha  # noqa: E402
from openalex.client import OpenAlexError, fetch_papers  # noqa: E402
from openalex.journals import source_id_filter  # noqa: E402
from papers.qa_poll import poll_burst  # noqa: E402
from papers.qa_state import save_current_paper  # noqa: E402
from papers.store import load_sent, mark_sent  # noqa: E402
from pdf.client import resolve_pdf  # noqa: E402
from relevance.client import RelevanceError, evaluate_papers  # noqa: E402
from telegram.client import TelegramError, send_telegram_document, send_telegram_message  # noqa: E402

YEARS_BACK = 10
N_CANDIDATES = 20
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", ".pdf_downloads")


def _send(mailto: str, bot_token: str, chat_id: str) -> None:
    from_year = date.today().year - YEARS_BACK

    print("Paso 1/4: trayendo candidatos de OpenAlex...")
    try:
        papers = fetch_papers(
            source_ids=source_id_filter(),
            from_year=from_year,
            limit=N_CANDIDATES,
            sort="publication_date:desc",
        )
    except OpenAlexError as e:
        sys.exit(f"Error consultando OpenAlex: {e}")

    sent = load_sent()
    candidates = [p for p in papers if p.abstract and p.openalex_id not in sent]
    skipped = len(papers) - len(candidates)
    print(f"{len(papers)} candidatos ({skipped} sin abstract o ya enviados, se omiten).")

    if not candidates:
        print("Nada nuevo para evaluar en esta corrida.")
        return

    print(f"\nPaso 2/4: evaluando relevancia + importancia de {len(candidates)} candidatos...")
    try:
        assessment = evaluate_papers(candidates)
    except RelevanceError as e:
        sys.exit(f"Error evaluando relevancia: {e}")

    if assessment.top_pick_index is None:
        print("Ningun candidato fue suficientemente relevante/importante en esta corrida.")
        return

    top = candidates[assessment.top_pick_index]
    print(f"Top pick: {top.title}")
    print(f"Razon: {assessment.top_pick_reasoning}\n")

    print("Paso 3/4: consiguiendo el PDF...")
    pdf_result = resolve_pdf(top, out_dir=OUT_DIR, unpaywall_email=mailto)
    if not pdf_result.local_path:
        sys.exit(
            f"No se pudo descargar el PDF ({pdf_result.notes}); "
            "no se puede generar la ficha ni enviar."
        )
    print(f"Fuente: {pdf_result.source} | archivo: {pdf_result.local_path}\n")

    print("Paso 4/4: generando la ficha y enviando por Telegram...")
    try:
        ficha = generate_ficha(top, pdf_result.local_path)
    except FichaError as e:
        sys.exit(f"Error generando la ficha: {e}")

    messages = format_ficha_message(ficha, top, top_pick_reasoning=assessment.top_pick_reasoning)
    try:
        for part in messages:
            send_telegram_message(part, chat_id=chat_id, bot_token=bot_token, parse_mode="HTML")
        send_telegram_document(pdf_result.local_path, chat_id=chat_id, bot_token=bot_token)
    except TelegramError as e:
        sys.exit(f"Error mandando por Telegram: {e}")

    mark_sent([top.openalex_id])
    save_current_paper(
        {
            "openalex_id": top.openalex_id,
            "title": top.title,
            "authors": top.authors,
            "journal": top.journal,
            "publication_year": top.publication_year,
            "doi": top.doi,
        },
        pdf_result.local_path,
    )
    print(f"\n=== Enviado: {top.title} ===")

    print("\nRafaga de preguntas: revisando cada 10s por 10 min (la mayoria de las")
    print("preguntas llegan poco despues de la notificacion)...")
    poll_burst(bot_token, chat_id)
    print("Rafaga terminada. El poll de fondo (cada 5 min) sigue cubriendo el resto del dia.")


def main() -> None:
    mailto = os.environ.get("OPENALEX_MAILTO")
    if not mailto:
        sys.exit("Falta OPENALEX_MAILTO en el entorno.")

    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN_PAPERS")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID_PAPERS")
    if not bot_token or not chat_id:
        sys.exit(
            "Faltan TELEGRAM_BOT_TOKEN_PAPERS y/o TELEGRAM_CHAT_ID_PAPERS en el entorno "
            "(bot separado del de oportunidades - ver README > Envío por Telegram)."
        )

    _send(mailto, bot_token, chat_id)


if __name__ == "__main__":
    main()
