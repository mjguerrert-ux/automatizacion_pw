"""
Store minimo para no reenviar por Telegram una oportunidad ya notificada en
una corrida anterior, y para la cola que limita el envio a 1 oportunidad por
corrida. Sin lo primero, cada corrida automatica (Parte F) volveria a mandar
las mismas fellowships que siguen abiertas; sin lo segundo, una corrida que
encuentra varias oportunidades relevantes las mandaria todas de una vez (paso
el 7/oct, demasiado para revisar).

Guarda apply_link (vistos) y fichas pendientes de enviar (cola), cada uno en
su propio JSON plano. No es una base de datos: para el volumen de este
pipeline (unas pocas oportunidades por corrida, unas pocas corridas por
semana) un archivo alcanza para cada cosa.
"""

from __future__ import annotations

import json
import os

_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data")
DEFAULT_STORE_PATH = os.path.join(_DATA_DIR, "opportunities_seen.json")
DEFAULT_QUEUE_PATH = os.path.join(_DATA_DIR, "opportunities_queue.json")


def load_seen(path: str = DEFAULT_STORE_PATH) -> set[str]:
    if not os.path.exists(path):
        return set()
    with open(path, encoding="utf-8") as f:
        return set(json.load(f))


def mark_seen(links: list[str], path: str = DEFAULT_STORE_PATH) -> None:
    seen = load_seen(path)
    seen.update(links)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(sorted(seen), f, ensure_ascii=False, indent=2)


def load_queue(path: str = DEFAULT_QUEUE_PATH) -> list[dict]:
    """Cola FIFO de oportunidades relevantes que todavia no se mandaron por
    Telegram (se manda como mucho 1 por corrida - ver send_opportunities.py).
    Cada item es un dict serializable con los campos de OpportunityFicha mas
    "title_raw" (para los logs)."""
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_queue(queue: list[dict], path: str = DEFAULT_QUEUE_PATH) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(queue, f, ensure_ascii=False, indent=2)
