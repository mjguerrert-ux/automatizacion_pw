"""
Prueba de humo de la Parte E: manda un mensaje de texto simple por WhatsApp
via Twilio, para validar que las credenciales y el numero destino funcionan
antes de conectar el envio real a los pipelines de papers/oportunidades.

Setup (una sola vez):
  1. Crear cuenta en https://www.twilio.com/ (el sandbox de WhatsApp es gratis).
  2. En la consola de Twilio, ir a Messaging > Try it out > Send a WhatsApp
     message, y unir tu numero al sandbox mandando el codigo indicado por
     WhatsApp al numero de sandbox de Twilio.
  3. Copiar Account SID y Auth Token de la consola.

Uso:
    TWILIO_ACCOUNT_SID=AC... TWILIO_AUTH_TOKEN=... \\
        TWILIO_WHATSAPP_TO=whatsapp:+573001234567 \\
        python scripts/send_test_whatsapp.py
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from whatsapp.client import WhatsAppError, send_whatsapp_message  # noqa: E402

TEST_MESSAGE = "✅ Prueba del sistema de oportunidades/papers académicos por WhatsApp."


def main() -> None:
    try:
        sid = send_whatsapp_message(TEST_MESSAGE)
    except WhatsAppError as e:
        sys.exit(f"Error: {e}")

    print(f"Mensaje enviado. SID: {sid}")


if __name__ == "__main__":
    main()
