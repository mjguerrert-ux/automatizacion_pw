"""
Parte B: filtro de relevancia + importancia sobre los abstracts, usando la API de Claude.

No decide nada sobre PDFs ni redacta la ficha final (eso es C y D). Su unico trabajo
es, dado un lote de papers candidatos (de la Parte A), decidir cuales son relevantes
para los temas prioritarios de la usuaria y cual es el mejor candidato para esta corrida,
siguiendo la regla de seleccion del spec (importancia/relevancia por encima de recencia).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

import anthropic

from openalex.client import Paper

DEFAULT_MODEL = "claude-opus-5"

PRIORITY_THEMES = [
    "poblacion_juvenil",
    "genero",
    "salud",
    "educacion",
    "inferencia_causal_aplicada",
    "inferencia_causal_metodologica",
]

SYSTEM_PROMPT = """\
Ayudas a triar papers academicos de economia para una investigadora colombiana.

## Contexto de la usuaria
- Investigadora y analista en la Secretaria de Educacion de Medellin, Laboratorio \
para la Calidad de la Educacion (Subsecretaria de Planeacion Educativa).
- Afiliada a la Universidad EAFIT.
- Trabaja con datos administrativos colombianos: SIMAT, SABER 11, RIPS, PILA.
- Proyectos activos: desercion escolar (modelo de grafos), evaluacion del PAE \
(alimentacion escolar), evaluacion del PEEP (proteccion psicosocial escolar), \
prevalencia de salud mental estudiantil, acceso a anticoncepcion de emergencia \
y capital humano.
- Esta aplicando a maestrias enfocadas en inferencia causal aplicada a temas \
sociales (Harvard MPA/ID, Chicago Harris MPP, Barcelona School of Economics).

## Temas prioritarios
- poblacion_juvenil
- genero
- salud (que sea interesante, no cualquier paper de salud)
- educacion
- inferencia_causal_aplicada: inferencia causal aplicada a los temas anteriores
- inferencia_causal_metodologica: papers teoricos/metodologicos que proponen \
nuevos estimadores o mejoras a estimadores existentes, sin importar el tema \
sustantivo al que se apliquen

## Regla de seleccion
- Prioridad: importancia/relevancia del paper por encima de que tan reciente sea.
- Si aparece un paper nuevo muy importante, ese se prioriza.
- Si no hay uno asi, un paper de hace unos anios (dentro del rango de 10 anios) \
tambien sirve.

## Tarea
Te doy una lista de papers candidatos (titulo, revista, anio, autores, abstract). \
Para cada uno:
1. is_relevant: si toca alguno de los temas prioritarios.
2. themes: con cual(es) tema(s) prioritario(s) se relaciona (vacio si no es relevante).
3. importance_score (0-10): importancia/relevancia del paper, NO que tan reciente es. \
Considera: aporte al campo, calidad de la identificacion causal si aplica, relevancia \
directa para los proyectos activos de la usuaria, y si es un paper metodologico \
importante en inferencia causal.
4. reasoning: una razon breve, en espanol.

Al final, identifica el mejor candidato para enviar en esta corrida (top_pick_index, \
el indice del paper) segun la regla de seleccion. top_pick_reasoning explica por que, \
en espanol, en MAXIMO 2 oraciones (esto se le muestra directo a la usuaria como el \
"por que te lo mando esta semana" al inicio del mensaje, asi que tiene que ser corto \
y concreto, no un resumen del paper - eso ya esta en la ficha). Si ningun paper es \
suficientemente relevante o importante, top_pick_index puede ser null.\
"""

_EVALUATION_SCHEMA = {
    "type": "object",
    "properties": {
        "evaluations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "paper_index": {"type": "integer"},
                    "is_relevant": {"type": "boolean"},
                    "themes": {
                        "type": "array",
                        "items": {"type": "string", "enum": PRIORITY_THEMES},
                    },
                    "importance_score": {"type": "integer"},
                    "reasoning": {"type": "string"},
                },
                "required": [
                    "paper_index",
                    "is_relevant",
                    "themes",
                    "importance_score",
                    "reasoning",
                ],
                "additionalProperties": False,
            },
        },
        "top_pick_index": {"type": ["integer", "null"]},
        "top_pick_reasoning": {"type": "string"},
    },
    "required": ["evaluations", "top_pick_index", "top_pick_reasoning"],
    "additionalProperties": False,
}


class RelevanceError(RuntimeError):
    pass


@dataclass
class PaperEvaluation:
    paper_index: int
    is_relevant: bool
    themes: list[str]
    importance_score: int
    reasoning: str


@dataclass
class RelevanceAssessment:
    evaluations: list[PaperEvaluation]
    top_pick_index: int | None
    top_pick_reasoning: str
    raw: dict = field(repr=False)


def _format_papers(papers: list[Paper]) -> str:
    blocks = []
    for i, p in enumerate(papers):
        authors = ", ".join(p.authors[:6]) + (" et al." if len(p.authors) > 6 else "")
        blocks.append(
            f"### Paper {i}\n"
            f"Titulo: {p.title}\n"
            f"Revista: {p.journal} ({p.publication_year})\n"
            f"Autores: {authors or '(sin autores listados)'}\n"
            f"Citas: {p.cited_by_count}\n"
            f"Abstract: {p.abstract or '(no disponible)'}"
        )
    return "\n\n".join(blocks)


def evaluate_papers(
    papers: list[Paper],
    model: str = DEFAULT_MODEL,
    effort: str = "medium",
    api_key: str | None = None,
) -> RelevanceAssessment:
    """Evalua relevancia + importancia de un lote de papers candidatos.

    `effort` por defecto es "medium": esto es una tarea de clasificacion sobre
    abstracts, no un problema de razonamiento profundo, asi que no hace falta
    "high"/"xhigh". Sube a "high" si ves evaluaciones poco cuidadosas.
    """
    if not papers:
        raise RelevanceError("No hay papers para evaluar.")

    client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()

    response = client.messages.create(
        model=model,
        max_tokens=8192,
        output_config={
            "effort": effort,
            "format": {"type": "json_schema", "schema": _EVALUATION_SCHEMA},
        },
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": _format_papers(papers)}],
    )

    if response.stop_reason == "refusal":
        raise RelevanceError(
            "Claude rechazo la solicitud de evaluacion "
            f"(stop_details={getattr(response, 'stop_details', None)})."
        )

    text = next((b.text for b in response.content if b.type == "text"), None)
    if text is None:
        raise RelevanceError("La respuesta no incluyo un bloque de texto con el JSON esperado.")

    data = json.loads(text)
    evaluations = [PaperEvaluation(**e) for e in data["evaluations"]]
    return RelevanceAssessment(
        evaluations=evaluations,
        top_pick_index=data["top_pick_index"],
        top_pick_reasoning=data["top_pick_reasoning"],
        raw=data,
    )
