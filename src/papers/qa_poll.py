"""
Logica compartida de "revisar si hay preguntas nuevas y responderlas", usada
tanto por el poll de fondo cada 5 min (scripts/answer_paper_questions.py,
via papers_qa.yml) como por la rafaga rapida justo despues de mandar un
paper (send_papers.py llama a poll_burst() antes de terminar el job).
"""

from __future__ import annotations

import time

from papers.qa import QaError, answer_question
from papers.qa_state import load_current_paper, load_offset, save_offset
from telegram.client import TelegramError, escape_html, get_updates, send_telegram_message

NO_PAPER_YET_MESSAGE = (
    "Todavía no te mandé ningún paper — cuando llegue el primero (por el cron "
    "de A→B→C→D) vas a poder preguntarme cosas sobre él acá."
)


def _extract_question(update: dict, chat_id: str) -> str | None:
    """Devuelve el texto de la pregunta si el update es un mensaje de texto
    normal (no un comando tipo /start) de la usuaria en el chat correcto;
    None si hay que ignorarlo (pero igual se consume el offset)."""
    message = update.get("message")
    if not message:
        return None
    if str(message.get("chat", {}).get("id")) != str(chat_id):
        return None
    text = message.get("text")
    if not text or text.startswith("/"):
        return None
    return text


def check_and_answer_once(bot_token: str, chat_id: str) -> int:
    """Revisa updates nuevos una vez y responde las preguntas de texto que
    encuentre. Devuelve cuantas preguntas respondio (0 si no habia nada)."""
    offset = load_offset()
    try:
        updates = get_updates(bot_token=bot_token, offset=offset)
    except TelegramError as e:
        print(f"Error consultando Telegram: {e}")
        return 0

    if not updates:
        return 0

    print(f"{len(updates)} update(s) nuevo(s).")
    current_paper = load_current_paper()
    answered = 0

    for update in updates:
        question = _extract_question(update, chat_id)
        if question:
            print(f"Pregunta: {question!r}")
            if current_paper is None:
                send_telegram_message(NO_PAPER_YET_MESSAGE, chat_id=chat_id, bot_token=bot_token)
            else:
                meta, pdf_path = current_paper
                try:
                    answer = answer_question(question, meta, pdf_path)
                except QaError as e:
                    print(f"  [FALLO] {e}")
                    send_telegram_message(
                        "No pude responder esa pregunta — hubo un error del lado de Claude. "
                        "Intentá de nuevo en un rato.",
                        chat_id=chat_id,
                        bot_token=bot_token,
                    )
                else:
                    try:
                        send_telegram_message(
                            f"<b>💬 {escape_html(question)}</b>\n\n{escape_html(answer)}",
                            chat_id=chat_id,
                            bot_token=bot_token,
                            parse_mode="HTML",
                        )
                        print("  [OK] respondida")
                        answered += 1
                    except TelegramError as e:
                        print(f"  [FALLO] enviando la respuesta: {e}")

        # Se consume el offset de TODOS los updates (respondidos, ignorados
        # o de otro chat) para no reprocesarlos en la proxima corrida.
        save_offset(update["update_id"] + 1)

    return answered


def poll_burst(
    bot_token: str,
    chat_id: str,
    duration_seconds: int = 600,
    interval_seconds: int = 10,
) -> None:
    """Rafaga de polling rapido justo despues de mandar un paper: la mayoria
    de las preguntas llegan poco despues de la notificacion, asi que vale la
    pena revisar cada `interval_seconds` (en vez de esperar al proximo ciclo
    del cron de 5 min) durante `duration_seconds`. Despues de esta ventana,
    el poll de fondo (papers_qa.yml, cada 5 min) sigue cubriendo preguntas
    tardias en el resto del dia/semana.

    Corre dentro del mismo job de GitHub Actions que mando el paper - no es
    un proceso aparte, asi que consume minutos de Actions (~10 min extra por
    corrida de envio) a cambio de respuestas casi inmediatas en la ventana
    donde son mas probables.
    """
    elapsed = 0
    while elapsed < duration_seconds:
        check_and_answer_once(bot_token, chat_id)
        time.sleep(interval_seconds)
        elapsed += interval_seconds
