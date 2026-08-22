"""
Parte B del pipeline de oportunidades: verificacion + extraccion de la ficha.

Toma los candidatos crudos de la Parte A (`opportunities.discovery`) y, para
cada uno, visita la pagina fuente (server tool `web_fetch`) para confirmar
que es una oportunidad real y vigente, decidir si encaja con los criterios
de la usuaria, y extraer los 8 campos de la ficha fija que se manda por
Telegram. No arma el mensaje en si: eso es `opportunities.format`.

Verifica en lotes (`batch_size` candidatos por llamada a la API), no todos
los candidatos en un solo turno: con muchos candidatos (ej. 42), un turno
que hace un `web_fetch` detras de otro para cada uno puede terminar en
`pause_turn` (turno largo que Claude corta a mitad de camino) antes de
devolver el JSON final - pasó en la corrida real del 22/08 con 42
candidatos. Si un lote entero falla (pause_turn, rechazo), se descarta ese
lote en vez de abortar toda la corrida (sus candidatos no quedan marcados
como vistos, asi que se reintentan solos en la proxima corrida).

El costo real no es tanto el modelo (`claude-sonnet-5` es barato por
token) sino la CANTIDAD de llamadas a herramientas dentro de un mismo
turno: cada `web_fetch`/`web_search` obliga a reenviar toda la
conversacion acumulada hasta ese punto para decidir el siguiente paso, asi
que el costo crece mucho mas rapido que lineal con el numero de llamadas.
En la corrida real del 22/08 (ver commit), 10 candidatos en 2 lotes de
batch_size=8 con max_uses escalado por lote (hasta 16 fetches + 8
busquedas por lote) costaron ~$3.47 en tokens de verificacion. Por eso
`batch_size` es chico (4) y los `max_uses` de las tools son topes FIJOS
bajos (no escalados por `len(batch)`), no solo para evitar `pause_turn`
sino para acotar cuantas llamadas puede encadenar una sola corrida.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import anthropic

from opportunities.discovery import BLOCKED_JOB_BOARD_DOMAINS, Candidate
from opportunities.usage import TokenUsage, usage_from_response

DEFAULT_MODEL = "claude-sonnet-5"
DEFAULT_BATCH_SIZE = 4

# Tope de contenido por pagina fetcheada: una convocatoria no necesita la
# pagina completa (con menu, footer, etc.) para extraer los 8 campos de la
# ficha, y cada pagina de mas que se ingiere entera es costo directo.
MAX_FETCH_CONTENT_TOKENS = 4000

# Topes FIJOS de llamadas a herramientas por lote (NO escalados por
# len(batch)): el costo real viene de la conversacion acumulada que se
# reenvia en cada llamada dentro del mismo turno, asi que mas llamadas
# permitidas = costo mucho mas que lineal, no solo mas candidatos cubiertos.
# 1 fetch por candidato del lote alcanza en el caso normal (discovery.py ya
# filtra a fuentes oficiales); el resto es margen para 1-2 candidatos que
# necesiten un fallback de busqueda.
MAX_FETCH_USES_PER_BATCH = DEFAULT_BATCH_SIZE
MAX_SEARCH_USES_PER_BATCH = 2

SYSTEM_PROMPT = """\
Verificas y estructuras oportunidades para una investigadora en economia \
con foco en educacion. Hay dos tracks igual de validos:

## Track 1: academico
- Tipo de posicion: fellowship pre-doctoral, o posicion de research \
assistant / RA. Universidad de origen: sin filtro, no importa cual sea.
- Foco tematico: el profesor/lab a cargo trabaja en educacion.
- Ejemplo de referencia: Embedded Development Lab (Harvard Graduate School \
of Education), profesor Vesall Nourani - fellowship pre-doctoral de \
educacion que, segun la usuaria, da prioridad a candidatos de paises de \
middle income. Lo que lo hace un buen ejemplo NO es que investigue sobre \
esos paises: es que el PROGRAMA prioriza candidatos que vienen de ahi.

## Track 2: entidades multilaterales / gubernamentales de desarrollo
- Tipo de posicion: research analyst, research assistant, consultant de \
investigacion (no administrativo/operativo), o programa de young \
professionals (ej. World Bank Young Professionals Program, IADB Young \
Professionals Program).
- Institucion: Banco Mundial, BID/IADB, CAF, OCDE, UNESCO, UNICEF (incl. \
Innocenti), u organismos analogos.
- Foco tematico: economia de la educacion (evaluaciones de impacto, \
politica educativa, analisis cuantitativo de programas educativos).
- Ejemplo de referencia: Research Analyst / Consultant en el equipo de \
Educacion del Banco Mundial (Education Global Practice) o del BID \
(Division de Educacion) - este tipo de organismos frecuentemente buscan \
diversidad geografica y dan preferencia a candidatos de sus paises \
miembro en desarrollo.

## Criterios de relevancia (aplica los DOS para el track que corresponda)
Cada candidato debe encajar en el tipo de posicion Y el foco tematico \
(educacion) de UNO de los dos tracks de arriba. No sirve un postdoc, \
profesor titular/senior, staff administrativo u operativo sin componente \
de investigacion, ni posiciones de maestria/PhD sin financiamiento como RA.

## Señal de prioridad para la usuaria (no es un criterio de relevancia)
La usuaria vive en Colombia. Si al visitar la pagina encuentras que el \
programa da preferencia, cupos reservados, o dice buscar candidatos de \
paises de middle income / en desarrollo / America Latina, Africa o Asia, \
menciona eso explicitamente en thematic_focus (ver campo 3 abajo) - es \
una senal fuerte a favor para ella. La AUSENCIA de esta senal no hace que \
el candidato sea irrelevante: la mayoria de fellowships/RA son abiertas a \
cualquier nacionalidad sin decirlo explicitamente.

## Fuentes: SOLO sitios oficiales
apply_link tiene que ser la pagina oficial de la universidad/lab u \
organismo, nunca un agregador de empleos (LinkedIn, Indeed, econjobmarket, \
predoc.org, etc.). Si al visitar source_url encuentras que en realidad es \
(o redirige a) un agregador, usa web_search para encontrar la pagina \
oficial de la misma convocatoria y usa esa URL como apply_link. Si no la \
encuentras, marca is_relevant=false.

## Tarea
Para cada candidato que te paso (con su source_url), usa la herramienta \
web_fetch para visitar esa URL y verificar la informacion real de la \
convocatoria. Si la pagina ya no esta disponible o la posicion ya cerro/fue \
llenada, marca is_relevant=false con el motivo. Si la URL no carga pero \
tienes evidencia solida en las notas de que la posicion es real y vigente, \
puedes usar web_search para intentar encontrar la pagina correcta.

Para cada candidato, evalua los criterios de arriba (is_relevant + \
reasoning en espanol, indicando a cual track corresponde) y, si es \
relevante, completa la ficha con estos 8 campos exactos, en espanol, \
listos para mandar por Telegram:

1. position: tipo y nombre exacto de la posicion.
2. institution: la institucion (universidad u organismo) y el profesor/ \
lab/division a cargo.
3. thematic_focus: foco tematico (1-2 oraciones). Si el programa da \
prioridad a candidatos de paises de middle income/en desarrollo, decilo \
explicitamente aca (ver arriba).
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
    def __init__(self, message: str, usage: TokenUsage | None = None):
        super().__init__(message)
        self.usage = usage or TokenUsage()


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
    model: str
    usage: TokenUsage
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


def _extract_batch(
    client: anthropic.Anthropic,
    batch: list[Candidate],
    model: str,
    effort: str,
) -> tuple[list[OpportunityEvaluation], dict, TokenUsage]:
    """Verifica un solo lote (una llamada a la API). candidate_index en el
    resultado es local al lote (0-indexado dentro de `batch`)."""
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
                "max_uses": MAX_FETCH_USES_PER_BATCH,
                "max_content_tokens": MAX_FETCH_CONTENT_TOKENS,
            },
            {
                "type": "web_search_20260209",
                "name": "web_search",
                "max_uses": MAX_SEARCH_USES_PER_BATCH,
                "blocked_domains": BLOCKED_JOB_BOARD_DOMAINS,
            },
        ],
        messages=[{"role": "user", "content": _format_candidates(batch)}],
    )

    usage = usage_from_response(response)

    if response.stop_reason == "refusal":
        raise ExtractError(
            "Claude rechazo la verificacion "
            f"(stop_details={getattr(response, 'stop_details', None)}).",
            usage=usage,
        )
    if response.stop_reason == "pause_turn":
        raise ExtractError(
            "La verificacion se pauso a mitad de camino (pause_turn) y este "
            "cliente no la reanuda automaticamente.",
            usage=usage,
        )

    text = next((b.text for b in response.content if b.type == "text"), None)
    if text is None:
        raise ExtractError(
            "La respuesta no incluyo un bloque de texto con el JSON esperado.", usage=usage
        )

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
    return evaluations, data, usage


def extract_fichas(
    candidates: list[Candidate],
    model: str = DEFAULT_MODEL,
    effort: str = "medium",
    api_key: str | None = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> ExtractResult:
    """Verifica cada candidato visitando su URL fuente y arma la ficha final.

    `model`/`effort` por defecto son el modelo economico (`claude-sonnet-5`) \
    y "medium": verificar una convocatoria contra dos condiciones y \
    extraer campos de una pagina ya fetcheada no necesita el modelo mas \
    caro. Subi a `claude-opus-5`/"high" si ves fichas de baja calidad.

    Llama a la API en lotes de `batch_size` candidatos (ver docstring del \
    modulo) en vez de mandar todos los candidatos en un solo turno. Si un \
    lote falla, se descarta y se sigue con el resto - no aborta la corrida \
    completa por un lote problematico.
    """
    if not candidates:
        raise ExtractError("No hay candidatos para verificar.")

    client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()

    all_evaluations: list[OpportunityEvaluation] = []
    raw_batches = []
    failed_batches = 0
    total_usage = TokenUsage()
    for start in range(0, len(candidates), batch_size):
        batch = candidates[start : start + batch_size]
        try:
            batch_evaluations, batch_raw, batch_usage = _extract_batch(
                client, batch, model, effort
            )
        except ExtractError as e:
            failed_batches += 1
            total_usage = total_usage + e.usage
            continue

        total_usage = total_usage + batch_usage
        for ev in batch_evaluations:
            all_evaluations.append(
                OpportunityEvaluation(
                    candidate_index=start + ev.candidate_index,
                    is_relevant=ev.is_relevant,
                    reasoning=ev.reasoning,
                    ficha=ev.ficha,
                )
            )
        raw_batches.append(batch_raw)

    if not all_evaluations:
        raise ExtractError(
            f"Los {failed_batches} lote(s) de verificacion fallaron (pause_turn/rechazo).",
            usage=total_usage,
        )

    return ExtractResult(
        evaluations=all_evaluations, model=model, usage=total_usage, raw={"batches": raw_batches}
    )
