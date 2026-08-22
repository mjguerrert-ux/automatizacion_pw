"""
Parte D: generacion de la ficha estructurada en espanol, leyendo el PDF
completo del paper con la API de Claude.

Hay DOS plantillas, porque un solo formato no le sirve igual de bien a un
paper aplicado (que responde una pregunta sustantiva con un metodo) que a uno
tecnico/metodologico (que propone o diagnostica el metodo en si mismo). Claude
decide cual aplica despues de leer el PDF completo (campo `tipo`).

Plantilla A - aplicados:
Titulo/autores, Pregunta, Contexto, Metodo, Identificacion, Efectos fijos y
controles, Mecanismos economicos, Resultados, Datos y muestra, Referencia,
PDF adjunto.

Plantilla B - tecnicos/metodologicos:
Titulo/autores, Pregunta, El problema, El argumento, Ilustracion empirica,
Que cambia en la practica, Que usar en su lugar, Referencia, PDF adjunto.

Titulo/autores y Referencia se arman con los metadatos de OpenAlex (Parte A),
no con lo que transcriba el modelo - la cita siempre es exacta. El resto de
campos los llena Claude leyendo el PDF completo.

El mensaje se manda en DOS partes de Telegram (format_ficha_message devuelve
una lista de 2 strings) para poder ser genuinamente explicativo en las
secciones mas conceptuales sin pelear contra el limite de 4096 caracteres
de un solo mensaje.
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from pathlib import Path

import anthropic

from openalex.client import Paper
from telegram.client import escape_html

DEFAULT_MODEL = "claude-opus-5"

SYSTEM_PROMPT = """\
Lees el PDF completo de un paper academico de economia y llenas una ficha de \
lectura en espanol, para una investigadora colombiana con formacion solida en \
inferencia causal (no hace falta explicarle que es un DiD o una VI: puedes usar \
la jerga tecnica con naturalidad, pero se preciso).

## Contexto de la usuaria (para calibrar tono y profundidad)
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

## Paso 1: elegi la plantilla (campo `tipo`)
- "aplicado": el paper responde una pregunta sustantiva (sobre educacion, salud, \
genero, poblacion juvenil, etc.) usando un metodo, aunque ese metodo sea \
sofisticado. El metodo es una herramienta, no el punto del paper.
- "tecnico": el paper propone, diagnostica o mejora un estimador/metodo en si \
mismo (ej. una descomposicion de un estimador existente, un nuevo estimador, \
una correccion a una practica estandar). La aplicacion empirica (si la hay) es \
secundaria - existe para ilustrar el punto tecnico, no es el objetivo del paper.

Todos los campos de texto de abajo van por Telegram, repartidos en DOS \
mensajes (cada uno con su propio limite de 4096 caracteres, asi que hay \
espacio de sobra - la prioridad ahora es que se ENTIENDA la idea, no la \
brevedad a cualquier costo). Cada limite de palabras sigue siendo un TECHO \
DURO - contalas antes de responder - pero es mucho mas generoso que antes: \
usalo. Es un limite de PALABRAS, no de oraciones: no lo cumplas escribiendo \
una sola oracion larguisima llena de comas, guiones y parentesis - preferi \
varias oraciones cortas que construyan la idea paso a paso. Toda cifra que \
des tiene que salir literalmente del PDF (no la inventes ni la redondees sin \
decir "aprox."). Las secciones se leen en orden, como una explicacion \
continua - cada una debe conectar con la anterior (ej. "por eso...", "esto \
implica que...", no un salto brusco de tema), no son campos sueltos e \
independientes. Nunca repitas entre campos lo que ya dijiste en otro.

CRITERIO GENERAL para identificacion, efectos_fijos_controles, mecanismos, \
resultados, el_problema, el_argumento y que_cambia_en_la_practica: no estas \
resumiendo el paper para alguien que ya lo entiende, estas EXPLICANDO la \
logica para que quede clara de una sola lectura. Si una idea depende de un \
concepto previo, no lo des por sentado - desarrollalo en una frase antes de \
usarlo. Si una analogia o un numero concreto ayuda a que la intuicion quede \
clara, usalo. Preferi "esto pasa porque X, y X pasa porque Y" a solo nombrar \
X. Al terminar de escribir cada uno de estos campos, releelo y preguntate: \
¿alguien que no elaboro este paper entenderia la logica completa con esto, o \
solo se entera de que existe? Si es lo segundo, reescribilo.

## Si tipo = "aplicado"

- pregunta (30 palabras maximo): que esta tratando de responder el paper.
- contexto (25 palabras maximo): lugar y anios del estudio (donde y cuando se \
recolectaron los datos o se dio el fenomeno estudiado, no el anio de publicacion).
- metodo (12 palabras maximo, etiqueta corta - NO una oracion completa): ej. \
"DiD con Callaway-Sant'Anna", "RD con discontinuidad en edad", "VI con shock de \
oferta".
- identificacion (110 palabras maximo): cual es el shock y cuales son las \
reglas de juego institucionales que generan la variacion que el paper explota, \
y POR QUE esa variacion permite aislar el efecto causal (que comparacion \
"limpia" queda armada, y de que amenaza a la identificacion protege). NO \
derives formulas ni hagas una descripcion paso a paso de un test estadistico - \
pero si explica la logica completa, no solo el nombre de la estrategia.
- efectos_fijos_controles: NO es un parrafo - es una lista, un bullet por \
cada efecto fijo o control relevante que use el paper, en este formato \
exacto por linea: "• <nombre del efecto fijo o control>: <que fuente de \
confusion especifica descarta y por que hace falta descartarla - la \
intuicion economica, no solo la mecanica estadistica>". Maximo 4 bullets \
(elegi los mas importantes si hay mas), ~25-35 palabras cada uno. Si el \
paper no usa un panel con efectos fijos (ej. es un experimento o una RD \
simple), el campo puede ser una sola oracion breve explicando por que no \
hacen falta, en vez de una lista.
- mecanismos (80 palabras maximo): la teoria economica de por que deberia \
pasar lo que el paper predice o encuentra - el "por que" normativo/teorico, NO \
el "como" tecnico (eso ya esta en identificacion). Desarrolla la cadena \
causal completa (ej. no digas solo "seleccion": explica que decision toman \
los agentes, con que informacion, y por que eso produce el patron que ves en \
los resultados).
- resultados (100 palabras maximo): el hallazgo principal, con la magnitud \
del efecto en unidades interpretables (puntos porcentuales, desviaciones \
estandar, pesos, anios de escolaridad, etc.) - nunca solo "el efecto es \
significativo". Interpreta la magnitud en terminos concretos (ej. "equivale \
a X" o comparado con la media de la variable) en vez de solo reportar el \
numero. Si hay muchas especificaciones alternativas, da el rango y que \
implica esa variacion (es robusto, o es fragil a la especificacion).
- datos_muestra (20 palabras maximo): fuente de los datos y tamanio de la \
muestra.

## Si tipo = "tecnico"

- pregunta (25 palabras maximo): el problema metodologico que ataca el paper - \
NO lo redactes como si fuera una pregunta de politica publica.
- el_problema (70 palabras maximo): que falla en la practica estandar actual, \
y POR QUE falla - construi la intuicion de la falla (que supuesto implicito \
se rompe, en que situacion concreta), no solo la afirmes.
- el_argumento (110 palabras maximo): el resultado tecnico central del paper, \
explicado en palabras (no en notacion) - que muestra el paper y por que eso \
es cierto, con la logica completa. Este es el corazon de la ficha: si hace \
falta, usa un ejemplo numerico simple o una analogia para que la intuicion \
quede clara, no solo el resultado formal.
- ilustracion_empirica (35 palabras maximo): el caso empirico que usan para \
mostrar el problema/argumento - es secundario, mencionalo brevemente (que \
pregunta sustantiva usan de ejemplo, no como si fuera el foco del paper).
- que_cambia_en_la_practica (80 palabras maximo): numeros concretos de la \
correccion - cuanto cambia una estimacion tipica al aplicar lo que propone \
el paper, en la ilustracion empirica u otro ejemplo que de el paper, e \
interpreta que tan grande es ese cambio en terminos practicos (cambia el \
signo, la magnitud, la significancia).
- que_usar_en_su_lugar (25 palabras maximo): el estimador, test o comando \
concreto que el paper recomienda usar en vez de la practica estandar (si el \
paper es puramente diagnostico y no prescribe una alternativa, decilo).

Escribe para un mensaje de chat: directo, sin relleno, sin frases como "en \
este paper los autores...". Ve al grano, pero sin sacrificar que la logica \
quede completa.\
"""

_APLICADO_SCHEMA = {
    "type": "object",
    "properties": {
        "tipo": {"const": "aplicado"},
        "pregunta": {"type": "string"},
        "contexto": {"type": "string"},
        "metodo": {"type": "string"},
        "identificacion": {"type": "string"},
        "efectos_fijos_controles": {"type": "string"},
        "mecanismos": {"type": "string"},
        "resultados": {"type": "string"},
        "datos_muestra": {"type": "string"},
    },
    "required": [
        "tipo",
        "pregunta",
        "contexto",
        "metodo",
        "identificacion",
        "efectos_fijos_controles",
        "mecanismos",
        "resultados",
        "datos_muestra",
    ],
    "additionalProperties": False,
}

_TECNICO_SCHEMA = {
    "type": "object",
    "properties": {
        "tipo": {"const": "tecnico"},
        "pregunta": {"type": "string"},
        "el_problema": {"type": "string"},
        "el_argumento": {"type": "string"},
        "ilustracion_empirica": {"type": "string"},
        "que_cambia_en_la_practica": {"type": "string"},
        "que_usar_en_su_lugar": {"type": "string"},
    },
    "required": [
        "tipo",
        "pregunta",
        "el_problema",
        "el_argumento",
        "ilustracion_empirica",
        "que_cambia_en_la_practica",
        "que_usar_en_su_lugar",
    ],
    "additionalProperties": False,
}

_FICHA_SCHEMA = {"anyOf": [_APLICADO_SCHEMA, _TECNICO_SCHEMA]}


class FichaError(RuntimeError):
    pass


@dataclass
class FichaContent:
    tipo: str  # "aplicado" | "tecnico"
    pregunta: str
    # Plantilla A (aplicado)
    contexto: str | None = None
    metodo: str | None = None
    identificacion: str | None = None
    efectos_fijos_controles: str | None = None
    mecanismos: str | None = None
    resultados: str | None = None
    datos_muestra: str | None = None
    # Plantilla B (tecnico)
    el_problema: str | None = None
    el_argumento: str | None = None
    ilustracion_empirica: str | None = None
    que_cambia_en_la_practica: str | None = None
    que_usar_en_su_lugar: str | None = None


def generate_ficha(
    paper: Paper,
    pdf_path: str,
    model: str = DEFAULT_MODEL,
    effort: str = "high",
    api_key: str | None = None,
) -> FichaContent:
    """Lee el PDF completo, elige la plantilla (aplicado/tecnico) y llena sus campos.

    `effort` por defecto es "high": a diferencia del filtro de relevancia
    (Parte B, que solo mira abstracts), esto implica leer un paper completo y
    entender su estrategia de identificacion con precision, asi que vale la
    pena el esfuerzo/costo extra.
    """
    pdf_bytes = Path(pdf_path).read_bytes()
    if not pdf_bytes:
        raise FichaError(f"El archivo {pdf_path} esta vacio.")
    pdf_b64 = base64.standard_b64encode(pdf_bytes).decode("utf-8")

    client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()

    user_content = [
        {
            "type": "document",
            "source": {"type": "base64", "media_type": "application/pdf", "data": pdf_b64},
        },
        {
            "type": "text",
            "text": (
                f"Titulo: {paper.title}\n"
                f"Autores: {', '.join(paper.authors) or '(desconocidos)'}\n"
                f"Revista: {paper.journal} ({paper.publication_year})\n\n"
                "Llena la ficha con base en el PDF adjunto."
            ),
        },
    ]

    with client.messages.stream(
        model=model,
        max_tokens=8192,
        system=SYSTEM_PROMPT,
        output_config={
            "effort": effort,
            "format": {"type": "json_schema", "schema": _FICHA_SCHEMA},
        },
        messages=[{"role": "user", "content": user_content}],
    ) as stream:
        response = stream.get_final_message()

    if response.stop_reason == "refusal":
        raise FichaError(
            f"Claude rechazo la solicitud (stop_details={getattr(response, 'stop_details', None)})."
        )

    text = next((b.text for b in response.content if b.type == "text"), None)
    if text is None:
        raise FichaError("La respuesta no incluyo un bloque de texto con el JSON esperado.")

    data = json.loads(text)
    return FichaContent(**data)




def _format_authors_for_reference(authors: list[str]) -> str:
    """Formato compacto para la cita: nombres completos si son pocos autores,
    "et al." si son varios - evita una lista larga de nombres completos sin
    depender de parsear apellidos (fragil con apellidos compuestos)."""
    if not authors:
        return "(autores desconocidos)"
    if len(authors) == 1:
        return authors[0]
    if len(authors) == 2:
        return f"{authors[0]} & {authors[1]}"
    if len(authors) == 3:
        return f"{authors[0]}, {authors[1]} & {authors[2]}"
    return f"{authors[0]} et al."


def _format_reference(paper: Paper) -> str:
    authors = _format_authors_for_reference(paper.authors)
    return f"{authors} ({paper.publication_year}). {paper.title}. {paper.journal}."


def _format_titulo_autores(paper: Paper) -> str:
    authors = _format_authors_for_reference(paper.authors)
    return f"{paper.title} — {authors} ({paper.publication_year})"


def _render_section(title: str, content: str) -> str:
    return f"<b>{title}</b>\n{escape_html(content)}"


def format_ficha_message(
    ficha: FichaContent,
    paper: Paper,
    top_pick_reasoning: str | None = None,
) -> list[str]:
    """Arma el texto final en HTML (parse_mode=HTML), como DOS mensajes
    listos para enviar por Telegram en secuencia (Parte E adjunta el PDF
    aparte, despues de estos dos). Se manda en dos partes para poder ser
    genuinamente explicativo en las secciones conceptuales sin pelear contra
    el limite de 4096 caracteres de un solo mensaje.

    Usa la plantilla A (aplicado) o B (tecnico) segun `ficha.tipo`.

    `top_pick_reasoning` es la razon (de la Parte B) de por que este paper se
    eligio sobre los demas candidatos de la corrida - sin esto, la usuaria
    recibe la ficha sin saber por que le llego justo este paper.
    """
    header = [f"📄 <b>{escape_html(_format_titulo_autores(paper))}</b>"]
    if top_pick_reasoning:
        header.append(f"🏆 <b>Por qué esta semana</b>\n{escape_html(top_pick_reasoning)}")

    if ficha.tipo == "aplicado":
        part1_sections = [
            ("📌 Pregunta", ficha.pregunta),
            ("📍 Contexto", ficha.contexto),
            ("🔧 Método", ficha.metodo),
            ("🎯 Identificación", ficha.identificacion),
            ("🎛️ Efectos fijos y controles", ficha.efectos_fijos_controles),
        ]
        part2_sections = [
            ("💡 Mecanismos económicos", ficha.mecanismos),
            ("📊 Resultados", ficha.resultados),
            ("📚 Datos y muestra", ficha.datos_muestra),
        ]
    elif ficha.tipo == "tecnico":
        part1_sections = [
            ("📌 Pregunta", ficha.pregunta),
            ("⚠️ El problema", ficha.el_problema),
            ("🧮 El argumento", ficha.el_argumento),
            ("🖼️ Ilustración empírica", ficha.ilustracion_empirica),
        ]
        part2_sections = [
            ("📊 Qué cambia en la práctica", ficha.que_cambia_en_la_practica),
            ("🛠️ Qué usar en su lugar", ficha.que_usar_en_su_lugar),
        ]
    else:
        raise FichaError(f"Tipo de ficha desconocido: {ficha.tipo!r}")

    part1 = "\n\n".join(header + [_render_section(t, c) for t, c in part1_sections])
    part2 = "\n\n".join(
        [_render_section(t, c) for t, c in part2_sections]
        + [
            f"📖 <b>Referencia</b>\n{escape_html(_format_reference(paper))}",
            "📎 PDF adjunto",
        ]
    )

    return [part1, part2]
