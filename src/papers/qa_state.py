"""
Estado del pipeline de preguntas y respuestas sobre papers (poll cada
~5 min via .github/workflows/papers_qa.yml):

- "paper actual": metadatos + PDF del ultimo paper que se mando por
  Telegram - es el contexto contra el que se responden las preguntas de la
  usuaria. Se pisa cada vez que send_papers.py manda un paper nuevo.
- offset de Telegram: el update_id a partir del cual pedir mensajes nuevos
  en la proxima corrida, para no volver a responder la misma pregunta.

Ninguno de los dos esta versionado (son estado, no codigo) - se persisten
entre corridas de GitHub Actions con actions/cache, igual que
papers_sent.json.
"""

from __future__ import annotations

import json
import os
import shutil

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data")
CURRENT_PAPER_DIR = os.path.join(DATA_DIR, "current_paper")
CURRENT_PAPER_META_PATH = os.path.join(CURRENT_PAPER_DIR, "meta.json")
CURRENT_PAPER_PDF_PATH = os.path.join(CURRENT_PAPER_DIR, "paper.pdf")
OFFSET_PATH = os.path.join(DATA_DIR, "telegram_offset_papers.json")


def save_current_paper(meta: dict, pdf_path: str) -> None:
    """`meta` debe tener al menos: title, authors (list[str]), journal,
    publication_year, doi - lo que generate_ficha/answer_question necesitan
    para dar contexto sin tener que volver a golpear OpenAlex."""
    os.makedirs(CURRENT_PAPER_DIR, exist_ok=True)
    with open(CURRENT_PAPER_META_PATH, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    shutil.copyfile(pdf_path, CURRENT_PAPER_PDF_PATH)


def load_current_paper() -> tuple[dict, str] | None:
    """Devuelve (meta, pdf_path) del ultimo paper enviado, o None si
    todavia no se mando ninguno (o el estado no persistio)."""
    if not os.path.exists(CURRENT_PAPER_META_PATH) or not os.path.exists(CURRENT_PAPER_PDF_PATH):
        return None
    with open(CURRENT_PAPER_META_PATH, encoding="utf-8") as f:
        meta = json.load(f)
    return meta, CURRENT_PAPER_PDF_PATH


def load_offset() -> int | None:
    if not os.path.exists(OFFSET_PATH):
        return None
    with open(OFFSET_PATH, encoding="utf-8") as f:
        return json.load(f).get("offset")


def save_offset(offset: int) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(OFFSET_PATH, "w", encoding="utf-8") as f:
        json.dump({"offset": offset}, f)
