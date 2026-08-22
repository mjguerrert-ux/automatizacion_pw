"""
Parte A del pipeline de oportunidades: descubrimiento de candidatos con la
herramienta de busqueda web de la API de Claude.

No hay un equivalente a OpenAlex para fellowships/posiciones de RA (no existe
una base de datos unica y estructurada), asi que este modulo usa el server
tool `web_search` para rastrear la web y proponer una lista amplia de
candidatos. Todavia no verifica cada candidato en detalle ni arma la ficha
final: eso es la Parte B (`opportunities.extract`).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import anthropic

DEFAULT_MODEL = "claude-opus-5"
DEFAULT_MAX_SEARCHES = 15

# Ejemplo de referencia para calibrar que tipo de oportunidad se busca. No es
# un filtro literal (no hay que limitarse a Harvard/Nourani): es el patron a
# reconocer en otras universidades/labs.
REFERENCE_EXAMPLE = """\
Embedded Development Lab (EDeL), Harvard Graduate School of Education, bajo \
el profesor Vesall Nourani: fellowship pre-doctoral con foco en formacion \
docente en Uganda y en la evaluacion del programa educativo SAT de FUNDAEC \
en Colombia.\
"""

SYSTEM_PROMPT = f"""\
Ayudas a una investigadora a encontrar oportunidades academicas que buscar \
manualmente seria muy lento: fellowships pre-doctorales y posiciones de \
research assistant (RA) que encajen con sus intereses.

## Que se busca
- Tipo de posicion: fellowship pre-doctoral, O posicion de research \
assistant / RA (full-time o part-time, remota o presencial).
- Universidad: sin filtro, cualquiera sirve. Lo que importa es el tema.
- Foco tematico: laboratorios o profesores que trabajan en educacion, \
particularmente investigacion educativa situada en (o centrada en) paises \
de middle income (ej. Uganda, Colombia, India, Kenia, Filipinas, etc). \
Tambien cuentan posiciones de educacion en general con un lab/PI activo en \
investigacion aplicada, aunque el pais especifico varie.

## Ejemplo de referencia (para calibrar el tipo de oportunidad, no para \
limitarte a ella)
{REFERENCE_EXAMPLE}

## Tarea
Usa la herramienta de busqueda web para encontrar posiciones ABIERTAS \
actualmente (o que abren pronto) de ese tipo. Busca en sitios de \
universidades (paginas de labs, "join our lab", "we're hiring"), en boletines \
de RA como econjobmarket/predoc.org, y en paginas de profesores de escuelas \
de educacion (Harvard GSE, Stanford GSE, etc.) y de economia del desarrollo \
que trabajen en educacion.

Para cada candidato que encuentres, reporta:
1. title_raw: el titulo/nombre de la posicion tal como aparece.
2. institution_raw: universidad y, si se menciona, el profesor/lab a cargo.
3. source_url: la URL exacta de la pagina donde encontraste la posicion \
(no un resultado de busqueda generico, sino el link a la convocatoria).
4. notes: cualquier detalle relevante que veas en el resultado de busqueda \
(foco tematico, paises, fecha limite) - se van a verificar despues \
visitando el link, asi que no hace falta que sean exhaustivas.

No incluyas posiciones claramente irrelevantes (postdoc, profesor titular, \
posiciones no academicas). Si tienes dudas sobre si algo encaja, inclúyelo \
igual: hay un paso posterior que filtra con mas cuidado.\
"""

_DISCOVERY_SCHEMA = {
    "type": "object",
    "properties": {
        "candidates": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title_raw": {"type": "string"},
                    "institution_raw": {"type": "string"},
                    "source_url": {"type": "string"},
                    "notes": {"type": "string"},
                },
                "required": ["title_raw", "institution_raw", "source_url", "notes"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["candidates"],
    "additionalProperties": False,
}


class DiscoveryError(RuntimeError):
    pass


@dataclass
class Candidate:
    title_raw: str
    institution_raw: str
    source_url: str
    notes: str


@dataclass
class DiscoveryResult:
    candidates: list[Candidate]
    raw: dict = field(repr=False)


def discover_opportunities(
    model: str = DEFAULT_MODEL,
    max_searches: int = DEFAULT_MAX_SEARCHES,
    effort: str = "high",
    api_key: str | None = None,
) -> DiscoveryResult:
    """Busca en la web candidatos de fellowships pre-doctorales / posiciones RA.

    `effort` por defecto es "high": encontrar y elegir buenas queries de \
    busqueda si se beneficia de mas razonamiento que un filtro de relevancia \
    sobre texto ya dado (Parte B del pipeline de papers).
    """
    client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()

    response = client.messages.create(
        model=model,
        max_tokens=16000,
        output_config={
            "effort": effort,
            "format": {"type": "json_schema", "schema": _DISCOVERY_SCHEMA},
        },
        system=SYSTEM_PROMPT,
        tools=[
            {
                "type": "web_search_20260209",
                "name": "web_search",
                "max_uses": max_searches,
            }
        ],
        messages=[
            {
                "role": "user",
                "content": (
                    "Busca oportunidades abiertas ahora mismo. Reporta todos los "
                    "candidatos plausibles que encuentres."
                ),
            }
        ],
    )

    if response.stop_reason == "refusal":
        raise DiscoveryError(
            "Claude rechazo la busqueda "
            f"(stop_details={getattr(response, 'stop_details', None)})."
        )
    if response.stop_reason == "pause_turn":
        raise DiscoveryError(
            "La busqueda se pauso a mitad de camino (pause_turn) y este cliente "
            "no la reanuda automaticamente. Baja max_searches o reintenta."
        )

    text = next((b.text for b in response.content if b.type == "text"), None)
    if text is None:
        raise DiscoveryError("La respuesta no incluyo un bloque de texto con el JSON esperado.")

    data = json.loads(text)
    candidates = [Candidate(**c) for c in data["candidates"]]
    return DiscoveryResult(candidates=candidates, raw=data)
