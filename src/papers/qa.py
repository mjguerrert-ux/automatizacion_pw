"""
Responde preguntas de seguimiento de la usuaria sobre el paper actual
(el ultimo que se le mando por Telegram), leyendo el PDF completo de nuevo.

No mantiene memoria conversacional entre preguntas distintas - cada pregunta
se responde de forma independiente, solo con el PDF como contexto. Si en el
futuro hace falta que recuerde preguntas anteriores dentro de la misma
"sesion" de un paper, hay que guardar el historial de turnos en
qa_state.py y pasarlo aca.
"""

from __future__ import annotations

import base64
from pathlib import Path

import anthropic

DEFAULT_MODEL = "claude-opus-5"

SYSTEM_PROMPT = """\
Respondes preguntas de una investigadora colombiana (Secretaria de Educacion \
de Medellin, formacion solida en inferencia causal) sobre un paper academico \
de economia cuyo PDF completo tenes adjunto. Ya le mandaste la ficha resumen \
de este paper antes; ahora esta preguntando algo puntual sobre el.

Respondes en espanol, directo y como en un chat (no un ensayo): anda al grano, \
basate estrictamente en el contenido del PDF (si el paper no responde la \
pregunta, decilo en vez de inventar), y usa la jerga tecnica con naturalidad \
(no hace falta explicarle que es un DiD o una VI).

Limite duro: el mensaje se manda por Telegram (4096 caracteres maximo). \
Apuntá a 100-150 palabras salvo que la pregunta pida explicitamente mas \
detalle o una lista larga - en ese caso podes usar hasta ~300 palabras, nunca \
mas.\
"""


class QaError(RuntimeError):
    pass


def answer_question(
    question: str,
    paper_meta: dict,
    pdf_path: str,
    model: str = DEFAULT_MODEL,
    effort: str = "medium",
    api_key: str | None = None,
) -> str:
    pdf_bytes = Path(pdf_path).read_bytes()
    if not pdf_bytes:
        raise QaError(f"El archivo {pdf_path} esta vacio.")
    pdf_b64 = base64.standard_b64encode(pdf_bytes).decode("utf-8")

    client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()

    authors = ", ".join(paper_meta.get("authors") or []) or "(desconocidos)"
    user_content = [
        {
            "type": "document",
            "source": {"type": "base64", "media_type": "application/pdf", "data": pdf_b64},
            # Cachea el procesamiento del PDF ~5 min: si la usuaria manda
            # varias preguntas seguidas sobre el mismo paper (el intervalo
            # tipico entre corridas del poll), las siguientes salen mas
            # rapido y mas baratas.
            "cache_control": {"type": "ephemeral"},
        },
        {
            "type": "text",
            "text": (
                f"Titulo: {paper_meta.get('title', '(desconocido)')}\n"
                f"Autores: {authors}\n"
                f"Revista: {paper_meta.get('journal', '(desconocida)')} "
                f"({paper_meta.get('publication_year', '?')})\n\n"
                f"Pregunta de la usuaria: {question}"
            ),
        },
    ]

    with client.messages.stream(
        model=model,
        max_tokens=2048,
        system=SYSTEM_PROMPT,
        output_config={"effort": effort},
        messages=[{"role": "user", "content": user_content}],
    ) as stream:
        response = stream.get_final_message()

    if response.stop_reason == "refusal":
        raise QaError(
            f"Claude rechazo la solicitud (stop_details={getattr(response, 'stop_details', None)})."
        )

    text = next((b.text for b in response.content if b.type == "text"), None)
    if text is None:
        raise QaError("La respuesta no incluyo un bloque de texto.")

    return text.strip()
