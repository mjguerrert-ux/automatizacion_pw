"""
Poll de preguntas sobre el paper actual: revisa si la usuaria le escribio
algo nuevo al bot de papers desde la ultima corrida y, si es una pregunta de
texto, la responde usando el PDF del ultimo paper que se le mando (Parte
D+E "conversacional").

Pensado para correr cada ~5 minutos via .github/workflows/papers_qa.yml -
no es un servidor: cada corrida revisa una vez y termina. Solo llama a la
API de Claude cuando hay una pregunta nueva de verdad (getUpdates es
gratis), asi que el costo de tenerlo corriendo en vacio es ~cero.

Uso:
    ANTHROPIC_API_KEY=sk-ant-... \\
        TELEGRAM_BOT_TOKEN_PAPERS=123456789:ABC-... TELEGRAM_CHAT_ID_PAPERS=... \\
        python scripts/answer_paper_questions.py
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from papers.qa import QaError, answer_question  # noqa: E402
from papers.qa_state import load_current_paper, load_offset, save_offset  # noqa: E402
from telegram.client import TelegramError, escape_html, get_updates, send_telegram_message  # noqa: E402

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


def main() -> None:
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN_PAPERS")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID_PAPERS")
    if not bot_token or not chat_id:
        sys.exit(
            "Faltan TELEGRAM_BOT_TOKEN_PAPERS y/o TELEGRAM_CHAT_ID_PAPERS en el entorno."
        )

    offset = load_offset()
    try:
        updates = get_updates(bot_token=bot_token, offset=offset)
    except TelegramError as e:
        sys.exit(f"Error consultando Telegram: {e}")

    if not updates:
        print("Sin mensajes nuevos.")
        return

    print(f"{len(updates)} update(s) nuevo(s).")
    current_paper = load_current_paper()

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
                    except TelegramError as e:
                        print(f"  [FALLO] enviando la respuesta: {e}")

        # Se consume el offset de TODOS los updates (respondidos, ignorados
        # o de otro chat) para no reprocesarlos en la proxima corrida.
        save_offset(update["update_id"] + 1)


if __name__ == "__main__":
    main()
