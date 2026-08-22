"""
Parte E del pipeline (compartida entre papers y oportunidades): envio de
mensajes por Telegram, via un bot personal.

A diferencia de WhatsApp Business (que exige verificacion de negocio en
Meta y una plantilla pre-aprobada para cualquier mensaje que el bot inicie
sin que el destinatario haya escrito antes), un bot de Telegram manda
mensajes libremente desde el primer minuto, sin aprobacion de nadie - encaja
mucho mejor con un sistema de notificacion personal como este.

Setup (una sola vez):
  1. Hablarle a @BotFather en Telegram, mandar /newbot, seguir las
     instrucciones (nombre + username del bot). Da un token, formato
     "123456789:ABC-...".
  2. Buscar tu bot nuevo por el username que le pusiste y mandarle
     CUALQUIER mensaje (ej. "hola") - Telegram no deja que un bot le mande
     mensajes a un chat que nunca le escribio primero.
  3. Abrir https://api.telegram.org/bot<TOKEN>/getUpdates en el navegador
     (reemplazando <TOKEN>) y buscar tu chat_id en la respuesta
     (result[0].message.chat.id).
"""

from __future__ import annotations

import os

import requests

API_BASE = "https://api.telegram.org"

# Limite de caracteres por mensaje de Telegram.
MAX_TEXT_LENGTH = 4096


class TelegramError(RuntimeError):
    pass


def escape_html(text: str) -> str:
    """Telegram (parse_mode=HTML) solo reserva estos 3 caracteres - hay que
    escaparlos en cualquier texto dinamico (generado por el modelo, o
    metadatos como titulo/autores) antes de insertarlo en un mensaje que use
    tags <b>/<i>/etc, para que un "&"/"<"/">" del contenido no rompa el
    parseo del mensaje."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def send_telegram_message(
    text: str,
    chat_id: str | None = None,
    bot_token: str | None = None,
    parse_mode: str | None = None,
) -> int:
    """Manda `text` por Telegram via el bot. Devuelve el message_id.

    `chat_id` y `bot_token` se toman de TELEGRAM_CHAT_ID / TELEGRAM_BOT_TOKEN
    si no se pasan explicitamente.

    `parse_mode`: None (default) manda texto plano - si `text` tiene
    caracteres tipo "*negrita*" o "<b>negrita</b>", Telegram los muestra
    LITERALES, no los renderiza (bug facil de no notar). Pasar "HTML" para
    que Telegram interprete tags <b>/<i>/etc; en ese caso, cualquier texto
    dinamico insertado en `text` debe venir ya escapado (ver
    ficha.client._escape_html) para que un "&"/"<"/">" del contenido no
    rompa el parseo.
    """
    bot_token = bot_token or os.environ.get("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        raise TelegramError(
            "Falta el token del bot. Define TELEGRAM_BOT_TOKEN (lo da "
            "@BotFather al crear el bot con /newbot)."
        )
    chat_id = chat_id or os.environ.get("TELEGRAM_CHAT_ID")
    if not chat_id:
        raise TelegramError(
            "Falta el chat_id destino. Define TELEGRAM_CHAT_ID (ver el "
            "docstring de este modulo para como obtenerlo con getUpdates)."
        )

    if len(text) > MAX_TEXT_LENGTH:
        raise TelegramError(
            f"El mensaje tiene {len(text)} caracteres; Telegram permite hasta "
            f"{MAX_TEXT_LENGTH} por mensaje. Acortalo antes de mandar."
        )

    payload = {"chat_id": chat_id, "text": text}
    if parse_mode:
        payload["parse_mode"] = parse_mode

    try:
        resp = requests.post(
            f"{API_BASE}/bot{bot_token}/sendMessage",
            json=payload,
            timeout=30,
        )
        data = resp.json()
    except requests.RequestException as e:
        raise TelegramError(f"Error de red mandando el mensaje por Telegram: {e}") from e

    if not data.get("ok"):
        raise TelegramError(f"Error mandando el mensaje por Telegram: {data}")

    return data["result"]["message_id"]


def send_telegram_document(
    file_path: str,
    caption: str | None = None,
    chat_id: str | None = None,
    bot_token: str | None = None,
) -> int:
    """Manda el archivo en `file_path` como documento por Telegram (usado por
    el pipeline de papers para adjuntar el PDF completo). Devuelve el
    message_id.

    `caption` va como texto acompañando el documento (limite de Telegram:
    1024 caracteres, mas corto que el de un mensaje de texto suelto) - para
    la ficha completa, mandala primero con send_telegram_message y usa este
    `caption` solo para algo breve, o dejalo en None.
    """
    bot_token = bot_token or os.environ.get("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        raise TelegramError(
            "Falta el token del bot. Define TELEGRAM_BOT_TOKEN (lo da "
            "@BotFather al crear el bot con /newbot)."
        )
    chat_id = chat_id or os.environ.get("TELEGRAM_CHAT_ID")
    if not chat_id:
        raise TelegramError(
            "Falta el chat_id destino. Define TELEGRAM_CHAT_ID (ver el "
            "docstring de este modulo para como obtenerlo con getUpdates)."
        )

    data = {"chat_id": chat_id}
    if caption:
        data["caption"] = caption[:1024]

    try:
        with open(file_path, "rb") as f:
            resp = requests.post(
                f"{API_BASE}/bot{bot_token}/sendDocument",
                data=data,
                files={"document": f},
                timeout=60,
            )
        result = resp.json()
    except (requests.RequestException, OSError) as e:
        raise TelegramError(f"Error mandando el documento por Telegram: {e}") from e

    if not result.get("ok"):
        raise TelegramError(f"Error mandando el documento por Telegram: {result}")

    return result["result"]["message_id"]


def get_updates(
    bot_token: str | None = None,
    offset: int | None = None,
    timeout: int = 0,
) -> list[dict]:
    """Trae mensajes nuevos del bot (usado por el polling de preguntas sobre
    papers). `offset` es el update_id a partir del cual traer (Telegram
    interpreta cualquier update con id < offset como ya leido/confirmado del
    lado del servidor) - guardar `ultimo_update_id + 1` entre corridas evita
    reprocesar el mismo mensaje.

    `timeout` es long-polling del lado de Telegram (segundos que el request
    espera si no hay updates nuevos) - se deja en 0 (no bloqueante) porque
    esto se llama desde un cron periodico, no un proceso siempre corriendo.
    """
    bot_token = bot_token or os.environ.get("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        raise TelegramError(
            "Falta el token del bot. Define TELEGRAM_BOT_TOKEN (lo da "
            "@BotFather al crear el bot con /newbot)."
        )

    params = {"timeout": timeout}
    if offset is not None:
        params["offset"] = offset

    try:
        resp = requests.get(
            f"{API_BASE}/bot{bot_token}/getUpdates",
            params=params,
            timeout=timeout + 30,
        )
        data = resp.json()
    except requests.RequestException as e:
        raise TelegramError(f"Error de red consultando updates de Telegram: {e}") from e

    if not data.get("ok"):
        raise TelegramError(f"Error consultando updates de Telegram: {data}")

    return data["result"]
