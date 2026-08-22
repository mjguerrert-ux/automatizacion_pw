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

DEFAULT_MODEL = "claude-sonnet-5"
DEFAULT_MAX_SEARCHES = 15

# Bolsas de empleo / agregadores: bloqueados de la busqueda porque la
# oportunidad tiene que reportarse con la URL de la fuente oficial (pagina
# de la universidad/lab, o del organismo), no la del agregador que la
# indexa. econjobmarket/predoc.org, LinkedIn, Indeed, etc. sirven para
# encontrar candidatos pero no como fuente final.
BLOCKED_JOB_BOARD_DOMAINS = [
    "linkedin.com",
    "indeed.com",
    "glassdoor.com",
    "ziprecruiter.com",
    "simplyhired.com",
    "idealist.org",
    "reliefweb.int",
    "devex.com",
    "unjobs.org",
    "higheredjobs.com",
    "insidehighered.com",
    "chronicle.com",
    "jobs.ac.uk",
    "academicpositions.com",
    "econjobmarket.org",
    "predoc.org",
]

# Ejemplos de referencia para calibrar que tipo de oportunidad se busca. No
# son un filtro literal (no hay que limitarse a estas instituciones/personas):
# son el patron a reconocer en otras universidades/labs/organismos.
REFERENCE_EXAMPLE_ACADEMIC = """\
Embedded Development Lab (EDeL), Harvard Graduate School of Education, bajo \
el profesor Vesall Nourani: fellowship pre-doctoral con foco en formacion \
docente en Uganda y en la evaluacion del programa educativo SAT de FUNDAEC \
en Colombia.\
"""

REFERENCE_EXAMPLE_MULTILATERAL = """\
Research Analyst / Consultant en el equipo de Educacion del Banco Mundial \
(Education Global Practice) o del Banco Interamericano de Desarrollo \
(Division de Educacion), apoyando evaluaciones de impacto y analisis \
cuantitativo de politica educativa en paises en desarrollo.\
"""

SYSTEM_PROMPT = f"""\
Ayudas a una investigadora a encontrar oportunidades que buscar \
manualmente seria muy lento. Hay dos tracks igual de validos, ambos en \
economia con foco en educacion:

## Track 1: academico
- Tipo de posicion: fellowship pre-doctoral, o posicion de research \
assistant / RA (full-time o part-time, remota o presencial).
- Universidad: sin filtro, cualquiera sirve. Lo que importa es el tema.
- Foco tematico (el criterio mas importante): laboratorios o profesores \
que trabajan en educacion, con investigacion situada en (o centrada en) \
paises de middle income (ej. Uganda, Colombia, India, Kenia, Filipinas, \
etc). Cuanto mas se parezca al ejemplo de referencia (educacion + middle \
income especifico), mejor candidato es.
- Ejemplo de referencia: {REFERENCE_EXAMPLE_ACADEMIC}

## Track 2: entidades multilaterales / gubernamentales de desarrollo
- Tipo de posicion: research analyst, research assistant, consultant \
(de investigacion, no administrativo), o programa de young professionals \
(ej. World Bank Young Professionals Program, IADB Young Professionals \
Program), en el area de economia con foco especial en educacion.
- Instituciones: Banco Mundial (World Bank), Banco Interamericano de \
Desarrollo (BID/IADB), CAF - Banco de Desarrollo de America Latina, OCDE, \
UNESCO, UNICEF (incl. UNICEF Innocenti), y organismos analogos. Sin \
filtro adicional de pais dentro de estas instituciones (por su mandato, \
casi todo lo que hacen ya es sobre paises en desarrollo/middle income).
- Foco tematico (el criterio mas importante): educacion especificamente \
— evaluaciones de impacto, politica educativa, analisis cuantitativo de \
programas educativos. Prioriza posiciones de educacion por encima de \
otras areas de estos organismos (salud, infraestructura, macro, etc.).
- Ejemplo de referencia: {REFERENCE_EXAMPLE_MULTILATERAL}

## Fuentes: SOLO sitios oficiales, nada de bolsas de empleo
Cada candidato tiene que venir de la pagina oficial de la universidad/lab \
o del organismo (ej. un dominio de la universidad, o worldbank.org, \
iadb.org, caf.com, oecd.org, unesco.org, unicef.org) — nunca de un \
agregador de empleos (LinkedIn, Indeed, econjobmarket, predoc.org, etc.). \
Si encuentras la mencion de una oportunidad en un agregador, segui el \
rastro hasta la pagina oficial de la convocatoria y reporta esa URL, no \
la del agregador. Si no encontras la pagina oficial, descarta el candidato.

## Tarea
Usa la herramienta de busqueda web para encontrar posiciones ABIERTAS \
actualmente (o que abren pronto) de cualquiera de los dos tracks. Para el \
track academico, busca directamente en sitios de universidades (paginas \
de labs, "join our lab", "we're hiring") y en paginas de profesores de \
escuelas de educacion (Harvard GSE, Stanford GSE, etc.) y de economia del \
desarrollo que trabajen en educacion. Para el track multilateral, busca \
directamente en los portales de empleo/consultoria de cada institucion \
(ej. jobs.worldbank.org, BID careers/talento, CAF empleos, OCDE careers, \
UNESCO/UNICEF careers) filtrando por educacion.

Para cada candidato que encuentres, reporta:
1. title_raw: el titulo/nombre de la posicion tal como aparece.
2. institution_raw: universidad y, si se menciona, el profesor/lab a cargo.
3. source_url: la URL exacta de la pagina OFICIAL donde encontraste la \
posicion (no un resultado de busqueda generico ni un agregador de empleos, \
sino el link a la convocatoria en el sitio de la universidad/organismo).
4. notes: cualquier detalle relevante que veas en el resultado de busqueda \
(foco tematico, paises, fecha limite) - se van a verificar despues \
visitando el link, asi que no hace falta que sean exhaustivas.

No incluyas posiciones claramente fuera de los dos tracks (postdoc, \
profesor titular/senior, staff administrativo o de operaciones sin \
componente de investigacion). Si tienes dudas sobre si algo encaja \
tematicamente, inclúyelo igual: hay un paso posterior que filtra con mas \
cuidado. Lo que SI hay que descartar sin dudar es cualquier candidato cuya \
unica fuente sea un agregador de empleos.\
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
    effort: str = "medium",
    api_key: str | None = None,
) -> DiscoveryResult:
    """Busca en la web candidatos de fellowships pre-doctorales / posiciones RA.

    `model`/`effort` por defecto son el modelo economico (`claude-sonnet-5`) \
    y "medium": esto es una busqueda + clasificacion, no una tarea que se \
    beneficie de mas razonamiento que eso. Subi a `claude-opus-5`/"high" si \
    ves que los candidatos que encuentra son de baja calidad.
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
                "blocked_domains": BLOCKED_JOB_BOARD_DOMAINS,
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
