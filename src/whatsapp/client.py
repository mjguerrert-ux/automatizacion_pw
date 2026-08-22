"""
Parte E del pipeline (compartida entre papers y oportunidades): envio de
mensajes por WhatsApp via la API de Twilio.

WhatsApp exige plantilla aprobada por Meta (content_sid) para cualquier
mensaje que INICIE la conversacion (nuestro caso: el cron manda sin que la
usuaria haya escrito antes) - texto libre (`body`) solo funciona como
respuesta dentro de una ventana de 24h despues de que el destinatario
escribe, y el sandbox de Twilio no soporta templates propios (solo sirve
para probar manualmente, respondiendo dentro de esa ventana). Por eso este
modulo expone las dos formas de mandar:

- send_whatsapp_message: texto libre. Sirve para pruebas manuales contra el
  sandbox (unido por codigo "join") o para responder dentro de una sesion.
- send_whatsapp_template: manda con una plantilla aprobada (content_sid).
  Es la que hay que usar para el envio automatico real (Parte F).

Requiere una cuenta de Twilio con un WhatsApp sender registrado (o el
sandbox, para pruebas). Ver
https://www.twilio.com/docs/whatsapp/quickstart/python y
https://www.twilio.com/docs/whatsapp/self-sign-up.
"""

from __future__ import annotations

import json
import os

from twilio.base.exceptions import TwilioException
from twilio.rest import Client

# Numero de sandbox de Twilio, compartido por todos los que usan el sandbox
# (solo entrega mensajes a numeros que ya se unieron a ese sandbox).
DEFAULT_SANDBOX_FROM = "whatsapp:+14155238886"

# Limite de caracteres por mensaje de texto libre de WhatsApp via Twilio.
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
            "directamente a la funcion de envio."
        )
    return Client(account_sid, auth_token)


def _resolve_to_from(to: str | None, from_: str | None) -> tuple[str, str]:
    to = to or os.environ.get("TWILIO_WHATSAPP_TO")
    if not to:
        raise WhatsAppError(
            "Falta el numero destino. Pasa to=... o define TWILIO_WHATSAPP_TO "
            "(formato 'whatsapp:+<codigo de pais><numero>', ej. "
            "'whatsapp:+573001234567')."
        )
    from_ = from_ or os.environ.get("TWILIO_WHATSAPP_FROM") or DEFAULT_SANDBOX_FROM
    return to, from_


def send_whatsapp_message(
    body: str,
    to: str | None = None,
    from_: str | None = None,
    account_sid: str | None = None,
    auth_token: str | None = None,
) -> str:
    """Manda `body` como texto libre por WhatsApp via Twilio. Devuelve el SID.

    Solo funciona como respuesta dentro de una sesion de 24h abierta por el
    destinatario (o contra el sandbox, luego de unirse con "join"). Para el
    envio automatico sin sesion previa, usar send_whatsapp_template.

    `to` y `from_` llevan el prefijo "whatsapp:" (ej. "whatsapp:+573001234567").
    Si no se pasan, se toman de TWILIO_WHATSAPP_TO / TWILIO_WHATSAPP_FROM.
    Si tampoco hay TWILIO_WHATSAPP_FROM, se usa el numero de sandbox de Twilio.
    """
    to, from_ = _resolve_to_from(to, from_)

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


def send_whatsapp_template(
    content_sid: str,
    content_variables: dict[str, str],
    to: str | None = None,
    from_: str | None = None,
    account_sid: str | None = None,
    auth_token: str | None = None,
) -> str:
    """Manda un mensaje de WhatsApp con una plantilla aprobada por Meta.

    Es la forma correcta de mandar mensajes que la usuaria no pidio (el cron
    de la Parte F, que no responde a nada) - WhatsApp exige que estos vengan
    en una plantilla pre-aprobada, no como texto libre.

    `content_sid` es el ID de la plantilla (Twilio Console > Content Template
    Builder, empieza con "HX..."), ya aprobada por WhatsApp. `content_variables`
    mapea el numero de cada variable de la plantilla (como string, ej. "1")
    a su valor (ej. {"1": "Pre-doctoral Fellowship", "2": "..."}).
    """
    to, from_ = _resolve_to_from(to, from_)

    client = _client(account_sid, auth_token)
    try:
        message = client.messages.create(
            content_sid=content_sid,
            content_variables=json.dumps(content_variables),
            from_=from_,
            to=to,
        )
    except TwilioException as e:
        raise WhatsAppError(f"Error mandando el mensaje por WhatsApp: {e}") from e

    return message.sid
