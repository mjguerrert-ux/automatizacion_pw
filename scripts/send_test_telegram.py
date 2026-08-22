"""
Prueba de humo de la Parte E: manda un mensaje de texto simple por Telegram,
para validar que el token del bot y el chat_id funcionan antes de conectar
el envio real a los pipelines de papers/oportunidades.

Setup (una sola vez):
  1. Hablarle a @BotFather en Telegram, mandar /newbot, seguir las
     instrucciones. Da un token (formato "123456789:ABC-...").
  2. Buscar tu bot nuevo por su username y mandarle cualquier mensaje
     (ej. "hola") - un bot no puede escribirle primero a un chat.
  3. Abrir en el navegador https://api.telegram.org/bot<TOKEN>/getUpdates
     (con tu token) y copiar el chat_id de result[0].message.chat.id.

Uso:
    TELEGRAM_BOT_TOKEN=123456789:ABC-... TELEGRAM_CHAT_ID=... \\
        python scripts/send_test_telegram.py
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from telegram.client import TelegramError, send_telegram_message  # noqa: E402

TEST_MESSAGE = "✅ Prueba del sistema de oportunidades/papers académicos por Telegram."


def main() -> None:
    try:
        message_id = send_telegram_message(TEST_MESSAGE)
    except TelegramError as e:
        sys.exit(f"Error: {e}")

    print(f"Mensaje enviado. message_id: {message_id}")


if __name__ == "__main__":
    main()
