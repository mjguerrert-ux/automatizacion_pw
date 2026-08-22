"""
Parte E del pipeline (compartida entre papers y oportunidades): envio de
mensajes por WhatsApp via la API de Twilio.

Requiere una cuenta de Twilio con WhatsApp habilitado: el sandbox de Twilio
sirve para pruebas (el numero destino se une mandando el codigo que da la
consola de Twilio por WhatsApp), y un numero de WhatsApp Business verificado
para produccion. Ver https://www.twilio.com/docs/whatsapp/quickstart/python.
"""

from __future__ import annotations

import os

from twilio.base.exceptions import TwilioException
from twilio.rest import Client

# Numero de sandbox de Twilio, compartido por todos los que usan el sandbox
# (solo entrega mensajes a numeros que ya se unieron a ese sandbox).
DEFAULT_SANDBOX_FROM = "whatsapp:+14155238886"

# Limite de caracteres por mensaje de WhatsApp via Twilio.
MAX_BODY_LENGTH = 1600


class WhatsAppError(RuntimeError):
    pass


def _client(account_sid: str | None, auth_token: str | None) -> Client:
    account_sid = account_sid or os.environ.get("TWILIO_ACCOUNT_SID")
    auth_token = auth_token or os.environ.get("TWILIO_AUTH_TOKEN")
    if not account_sid or not auth_token:
        raise WhatsAppError(
            "Faltan credenciales de Twilio. Define TWILIO_ACCOUNT_SID y "
            "TWILIO_AUTH_TOKEN (Twilio Console > Account Info), o pasalas "
            "directamente a send_whatsapp_message()."
        )
    return Client(account_sid, auth_token)


def send_whatsapp_message(
    body: str,
    to: str | None = None,
    from_: str | None = None,
    account_sid: str | None = None,
    auth_token: str | None = None,
) -> str:
    """Manda `body` por WhatsApp via Twilio. Devuelve el message SID.

    `to` y `from_` llevan el prefijo "whatsapp:" (ej. "whatsapp:+573001234567").
    Si no se pasan, se toman de TWILIO_WHATSAPP_TO / TWILIO_WHATSAPP_FROM.
    Si tampoco hay TWILIO_WHATSAPP_FROM, se usa el numero de sandbox de
    Twilio (solo funciona si `to` ya se unio a ese sandbox).
    """
    to = to or os.environ.get("TWILIO_WHATSAPP_TO")
    if not to:
        raise WhatsAppError(
            "Falta el numero destino. Pasa to=... o define TWILIO_WHATSAPP_TO "
            "(formato 'whatsapp:+<codigo de pais><numero>', ej. "
            "'whatsapp:+573001234567')."
        )
    from_ = from_ or os.environ.get("TWILIO_WHATSAPP_FROM") or DEFAULT_SANDBOX_FROM

    if len(body) > MAX_BODY_LENGTH:
        raise WhatsAppError(
            f"El mensaje tiene {len(body)} caracteres; Twilio permite hasta "
            f"{MAX_BODY_LENGTH} por mensaje de WhatsApp. Acortalo antes de mandar."
        )

    client = _client(account_sid, auth_token)
    try:
        message = client.messages.create(body=body, from_=from_, to=to)
    except TwilioException as e:
        raise WhatsAppError(f"Error mandando el mensaje por WhatsApp: {e}") from e

    return message.sid
