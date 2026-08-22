"""
Parte B del pipeline de oportunidades: verificacion + extraccion de la ficha.

Toma los candidatos crudos de la Parte A (`opportunities.discovery`) y, para
cada uno, visita la pagina fuente (server tool `web_fetch`) para confirmar
que es una oportunidad real y vigente, decidir si encaja con los criterios
de la usuaria, y extraer los 8 campos de la ficha fija que se manda por
WhatsApp. No arma el mensaje de WhatsApp en si: eso es `opportunities.format`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import anthropic

from opportunities.discovery import Candidate

DEFAULT_MODEL = "claude-opus-5"

SYSTEM_PROMPT = """\
Verificas y estructuras oportunidades academicas para una investigadora: \
fellowships pre-doctorales y posiciones de research assistant (RA).

## Criterios de relevancia (aplica los DOS)
1. Tipo de posicion: fellowship pre-doctoral, o posicion de research \
assistant / RA. No sirve un postdoc, profesor titular/junior, staff \
administrativo, ni posiciones de maestria/PhD sin financiamiento como RA.
2. Foco tematico: el profesor/lab a cargo trabaja en educacion, y \
particularmente en investigacion educativa situada en (o centrada en) \
paises de middle income (ej. Uganda, Colombia, India, Kenia, Filipinas). \
Universidad de origen: sin filtro, no importa cual sea.

Ejemplo de referencia (el tipo de oportunidad que SI encaja): Embedded \
Development Lab (Harvard Graduate School of Education), profesor Vesall \
Nourani - fellowship pre-doctoral con foco en formacion docente en Uganda y \
en la evaluacion del programa SAT de FUNDAEC en Colombia.

## Tarea
Para cada candidato que te paso (con su source_url), usa la herramienta \
web_fetch para visitar esa URL y verificar la informacion real de la \
convocatoria. Si la pagina ya no esta disponible o la posicion ya cerro/fue \
llenada, marca is_relevant=false con el motivo. Si la URL no carga pero \
tienes evidencia solida en las notas de que la posicion es real y vigente, \
puedes usar web_search para intentar encontrar la pagina correcta.

Para cada candidato, evalua los dos criterios de arriba (is_relevant + \
reasoning en espanol) y, si es relevante, completa la ficha con estos \
8 campos exactos, en espanol, listos para mandar por WhatsApp:

1. position: tipo y nombre exacto de la posicion.
2. institution: universidad y el profesor/lab a cargo.
3. thematic_focus: foco tematico (1-2 oraciones).
4. countries: paises involucrados (si no se especifica ninguno en \
particular, di "no especificado").
5. funding: salario/financiamiento (si no se especifica, di "no \
especificado").
6. deadline: fecha limite en formato legible (ej. "15 de marzo de 2026"). \
Si no hay fecha limite indicada, o la convocatoria esta siempre abierta, \
usa exactamente "no especificada".
7. requirements: lista corta (3-6 items) de los requisitos clave.
8. apply_link: el link directo para aplicar (o, si no hay uno especifico, \
el link a la pagina de la convocatoria).

Si is_relevant es false, deja los campos de la ficha con valores vacios \
("" o listas vacias) - no hace falta completarlos.\
"""

_EXTRACT_SCHEMA = {
    "type": "object",
    "properties": {
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "candidate_index": {"type": "integer"},
                    "is_relevant": {"type": "boolean"},
                    "reasoning": {"type": "string"},
                    "position": {"type": "string"},
                    "institution": {"type": "string"},
                    "thematic_focus": {"type": "string"},
                    "countries": {"type": "string"},
                    "funding": {"type": "string"},
                    "deadline": {"type": "string"},
                    "requirements": {"type": "array", "items": {"type": "string"}},
                    "apply_link": {"type": "string"},
                },
                "required": [
                    "candidate_index",
                    "is_relevant",
                    "reasoning",
                    "position",
                    "institution",
                    "thematic_focus",
                    "countries",
                    "funding",
                    "deadline",
                    "requirements",
                    "apply_link",
                ],
                "additionalProperties": False,
            },
        },
    },
    "required": ["results"],
    "additionalProperties": False,
}


class ExtractError(RuntimeError):
    pass


@dataclass
class OpportunityFicha:
    position: str
    institution: str
    thematic_focus: str
    countries: str
    funding: str
    deadline: str
    requirements: list[str]
    apply_link: str


@dataclass
class OpportunityEvaluation:
    candidate_index: int
    is_relevant: bool
    reasoning: str
    ficha: OpportunityFicha | None


@dataclass
class ExtractResult:
    evaluations: list[OpportunityEvaluation]
    raw: dict = field(repr=False)


def _format_candidates(candidates: list[Candidate]) -> str:
    blocks = []
    for i, c in enumerate(candidates):
        blocks.append(
            f"### Candidato {i}\n"
            f"Titulo (crudo): {c.title_raw}\n"
            f"Institucion (cruda): {c.institution_raw}\n"
            f"URL fuente: {c.source_url}\n"
            f"Notas: {c.notes or '(sin notas)'}"
        )
    return "\n\n".join(blocks)


def extract_fichas(
    candidates: list[Candidate],
    model: str = DEFAULT_MODEL,
    effort: str = "high",
    api_key: str | None = None,
) -> ExtractResult:
    """Verifica cada candidato visitando su URL fuente y arma la ficha final.

    `effort` por defecto es "high": decidir relevancia con criterio (dos \
    condiciones simultaneas) y extraer datos precisos de paginas reales se \
    beneficia de mas cuidado que una clasificacion simple sobre texto dado.
    """
    if not candidates:
        raise ExtractError("No hay candidatos para verificar.")

    client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()

    response = client.messages.create(
        model=model,
        max_tokens=16000,
        output_config={
            "effort": effort,
            "format": {"type": "json_schema", "schema": _EXTRACT_SCHEMA},
        },
        system=SYSTEM_PROMPT,
        tools=[
            {
                "type": "web_fetch_20260209",
                "name": "web_fetch",
                "max_uses": len(candidates) * 2,
            },
            {
                "type": "web_search_20260209",
                "name": "web_search",
                "max_uses": len(candidates),
            },
        ],
        messages=[{"role": "user", "content": _format_candidates(candidates)}],
    )

    if response.stop_reason == "refusal":
        raise ExtractError(
            "Claude rechazo la verificacion "
            f"(stop_details={getattr(response, 'stop_details', None)})."
        )
    if response.stop_reason == "pause_turn":
        raise ExtractError(
            "La verificacion se pauso a mitad de camino (pause_turn) y este "
            "cliente no la reanuda automaticamente. Prueba con menos candidatos."
        )

    text = next((b.text for b in response.content if b.type == "text"), None)
    if text is None:
        raise ExtractError("La respuesta no incluyo un bloque de texto con el JSON esperado.")

    data = json.loads(text)
    evaluations = []
    for r in data["results"]:
        ficha = None
        if r["is_relevant"]:
            ficha = OpportunityFicha(
                position=r["position"],
                institution=r["institution"],
                thematic_focus=r["thematic_focus"],
                countries=r["countries"],
                funding=r["funding"],
                deadline=r["deadline"] or "no especificada",
                requirements=r["requirements"],
                apply_link=r["apply_link"],
            )
        evaluations.append(
            OpportunityEvaluation(
                candidate_index=r["candidate_index"],
                is_relevant=r["is_relevant"],
                reasoning=r["reasoning"],
                ficha=ficha,
            )
        )
    return ExtractResult(evaluations=evaluations, raw=data)
