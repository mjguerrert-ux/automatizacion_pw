"""
Store minimo para no volver a mandar un paper ya enviado en una corrida
anterior. Sin esto, si el mismo paper sigue siendo el "top pick" (porque no
aparecio nada mas importante), Parte F lo reenviaria cada corrida.

Guarda solo los openalex_id ya enviados, en un JSON plano - mismo patron que
src/opportunities/store.py.
"""

from __future__ import annotations

import json
import os

DEFAULT_STORE_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "papers_sent.json"
)


def load_sent(path: str = DEFAULT_STORE_PATH) -> set[str]:
    if not os.path.exists(path):
        return set()
    with open(path, encoding="utf-8") as f:
        return set(json.load(f))


def mark_sent(openalex_ids: list[str], path: str = DEFAULT_STORE_PATH) -> None:
    sent = load_sent(path)
    sent.update(openalex_ids)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(sorted(sent), f, ensure_ascii=False, indent=2)
