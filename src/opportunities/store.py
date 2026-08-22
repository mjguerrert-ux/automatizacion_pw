"""
Store minimo para no reenviar por WhatsApp una oportunidad ya notificada en
una corrida anterior. Sin esto, cada corrida automatica (Parte F, todavia no
implementada) volveria a mandar las mismas fellowships que siguen abiertas.

Guarda solo los apply_link ya notificados, en un JSON plano. No es una base
de datos: para el volumen de este pipeline (unas pocas oportunidades por
corrida, unas pocas corridas por semana) un archivo alcanza.
"""

from __future__ import annotations

import json
import os

DEFAULT_STORE_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "opportunities_seen.json"
)


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
