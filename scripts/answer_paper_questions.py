"""
Poll de preguntas sobre el paper actual: revisa si la usuaria le escribio
algo nuevo al bot de papers desde la ultima corrida y, si es una pregunta de
texto, la responde usando el PDF del ultimo paper que se le mando (Parte
D+E "conversacional").

Pensado para correr cada ~5 minutos via .github/workflows/papers_qa.yml -
no es un servidor: cada corrida revisa una vez y termina. Solo llama a la
API de Claude cuando hay una pregunta nueva de verdad (getUpdates es
gratis), asi que el costo de tenerlo corriendo en vacio es ~cero.

(Justo despues de mandar un paper, send_papers.py hace ademas una rafaga de
chequeos cada 10s por 10 min - ver papers.qa_poll.poll_burst - porque la
mayoria de las preguntas llegan poco despues de la notificacion. Este script
es el que cubre el resto del tiempo.)

Uso:
    ANTHROPIC_API_KEY=sk-ant-... \\
        TELEGRAM_BOT_TOKEN_PAPERS=123456789:ABC-... TELEGRAM_CHAT_ID_PAPERS=... \\
        python scripts/answer_paper_questions.py
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from papers.qa_poll import check_and_answer_once  # noqa: E402


def main() -> None:
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN_PAPERS")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID_PAPERS")
    if not bot_token or not chat_id:
        sys.exit(
            "Faltan TELEGRAM_BOT_TOKEN_PAPERS y/o TELEGRAM_CHAT_ID_PAPERS en el entorno."
        )

    answered = check_and_answer_once(bot_token, chat_id)
    if answered == 0:
        print("Sin preguntas nuevas para responder.")


if __name__ == "__main__":
    main()
