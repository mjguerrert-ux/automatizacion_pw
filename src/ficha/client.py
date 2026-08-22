"""
Parte D: generacion de la ficha estructurada en espanol, leyendo el PDF
completo del paper con la API de Claude.

Hay DOS plantillas, porque un solo formato no le sirve igual de bien a un
paper aplicado (que responde una pregunta sustantiva con un metodo) que a uno
tecnico/metodologico (que propone o diagnostica el metodo en si mismo). Claude
decide cual aplica despues de leer el PDF completo (campo `tipo`).

Plantilla A - aplicados:
Titulo/autores, Pregunta, Contexto, Metodo, Identificacion, Efectos fijos y
controles, Mecanismos economicos, Resultados, Datos y muestra, Para tu
trabajo, Referencia, PDF adjunto.

Plantilla B - tecnicos/metodologicos:
Titulo/autores, Pregunta, El problema, El argumento, Ilustracion empirica,
Que cambia en la practica, Que usar en su lugar, Para tu trabajo, Referencia,
PDF adjunto.

Titulo/autores y Referencia se arman con los metadatos de OpenAlex (Parte A),
no con lo que transcriba el modelo - la cita siempre es exacta. El resto de
campos los llena Claude leyendo el PDF completo.
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

Todos los campos de texto de abajo van por Telegram: el mensaje completo no \
puede pasar de 4096 caracteres, y comparte espacio con un encabezado y una \
referencia. Cada limite de palabras es un TECHO DURO - contalas antes de \
responder. Es un limite de PALABRAS, no de oraciones: no lo cumplas escribiendo \
una sola oracion larguisima llena de comas, guiones y parentesis - si el paper \
tiene mucho detalle (formulas, muchas especificaciones, varios tests), CORTA \
contenido, no comprimas la sintaxis para que quepa todo. Ante la duda entre \
completitud y brevedad, elegi brevedad. Toda cifra que des tiene que salir \
literalmente del PDF (no la inventes ni la redondees sin decir "aprox."). Las \
secciones se leen en orden, como una explicacion continua - cada una debe \
conectar con la anterior (ej. "por eso...", "esto implica que...", no un salto \
brusco de tema), no son campos sueltos e independientes. Nunca repitas entre \
campos lo que ya dijiste en otro.

## Si tipo = "aplicado"

- pregunta (25 palabras maximo): que esta tratando de responder el paper.
- contexto (20 palabras maximo): lugar y anios del estudio (donde y cuando se \
recolectaron los datos o se dio el fenomeno estudiado, no el anio de publicacion).
- metodo (12 palabras maximo, etiqueta corta - NO una oracion completa): ej. \
"DiD con Callaway-Sant'Anna", "RD con discontinuidad en edad", "VI con shock de \
oferta".
- identificacion (50 palabras maximo): cual es el shock y cuales son las \
reglas de juego institucionales que generan la variacion que el paper explota. \
Explica COMO funciona la estrategia de identificacion en terminos generales - \
NO derives formulas, NO description paso a paso de un test estadistico.
- efectos_fijos_controles (40 palabras maximo): que efectos fijos/controles usa \
el paper y que interpretacion tienen - que fuente de confusion especifica \
descartan (no listes los nombres de las variables sin mas: interpreta que \
comparacion queda "limpia" gracias a cada uno). Si el paper no usa un panel \
con efectos fijos (ej. es un experimento o una RD simple), decilo brevemente \
en vez de forzar el campo.
- mecanismos (30 palabras maximo): la teoria economica de por que deberia \
pasar lo que el paper predice o encuentra - el "por que" normativo/teorico, NO \
el "como" tecnico (eso ya esta en identificacion).
- resultados (55 palabras maximo): el hallazgo principal, con la magnitud del \
efecto en unidades interpretables (puntos porcentuales, desviaciones estandar, \
pesos, anios de escolaridad, etc.) - nunca solo "el efecto es significativo". \
Si hay muchas especificaciones alternativas, da SOLO el rango, sin nombrar cada \
una.
- datos_muestra (18 palabras maximo): fuente de los datos y tamanio de la \
muestra.
- para_tu_trabajo (35 palabras maximo): conexion CONCRETA y especifica con el \
trabajo activo de la usuaria si el paper aplica - no te limites a nombrar el \
programa (PAE, PEEP, desercion, salud mental, anticoncepcion de emergencia, \
capital humano), di especificamente que deberia revisar o tener en cuenta en \
SU analisis por este paper. Si nada del paper conecta con su trabajo, comenta \
en cambio robustez o limites del estudio. No inventes conexiones ni \
limitaciones solo por llenar el campo.

## Si tipo = "tecnico"

- pregunta (20 palabras maximo): el problema metodologico que ataca el paper - \
NO lo redactes como si fuera una pregunta de politica publica.
- el_problema (40 palabras maximo): que falla en la practica estandar actual - \
por que el enfoque que todo el mundo usa hoy puede estar mal, y en que \
situacion especificamente.
- el_argumento (50 palabras maximo): el resultado tecnico central del paper, \
explicado en palabras (no en notacion) - que muestra el paper y por que eso \
es cierto, a alto nivel.
- ilustracion_empirica (30 palabras maximo): el caso empirico que usan para \
mostrar el problema/argumento - es secundario, mencionalo brevemente (que \
pregunta sustantiva usan de ejemplo, no como si fuera el foco del paper).
- que_cambia_en_la_practica (45 palabras maximo): numeros concretos de la \
correccion - cuanto cambia una estimacion tipica al aplicar lo que propone el \
paper, en la ilustracion empirica u otro ejemplo que de el paper.
- que_usar_en_su_lugar (25 palabras maximo): el estimador, test o comando \
concreto que el paper recomienda usar en vez de la practica estandar (si el \
paper es puramente diagnostico y no prescribe una alternativa, decilo).
- para_tu_trabajo (35 palabras maximo): que deberia revisar o cambiar la \
usuaria en SU trabajo (SIMAT, SABER 11, PAE, PEEP, desercion, salud mental, \
capital humano, etc.) a partir de este resultado tecnico - concreto y \
accionable, no una mencion generica del nombre del programa.

Escribe para un mensaje de chat: directo, sin relleno, sin frases como "en \
este paper los autores...". Ve al grano.\
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
        "para_tu_trabajo": {"type": "string"},
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
        "para_tu_trabajo",
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
        "para_tu_trabajo": {"type": "string"},
    },
    "required": [
        "tipo",
        "pregunta",
        "el_problema",
        "el_argumento",
        "ilustracion_empirica",
        "que_cambia_en_la_practica",
        "que_usar_en_su_lugar",
        "para_tu_trabajo",
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
    para_tu_trabajo: str
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


def format_ficha_message(
    ficha: FichaContent,
    paper: Paper,
    top_pick_reasoning: str | None = None,
) -> str:
    """Arma el texto final en HTML (parse_mode=HTML), listo para enviar por
    Telegram (Parte E adjunta el PDF aparte).

    Usa la plantilla A (aplicado) o B (tecnico) segun `ficha.tipo`.

    `top_pick_reasoning` es la razon (de la Parte B) de por que este paper se
    eligio sobre los demas candidatos de la corrida - sin esto, la usuaria
    recibe la ficha sin saber por que le llego justo este paper.
    """
    if ficha.tipo == "aplicado":
        sections = [
            ("📌 Pregunta", ficha.pregunta),
            ("📍 Contexto", ficha.contexto),
            ("🔧 Método", ficha.metodo),
            ("🎯 Identificación", ficha.identificacion),
            ("🎛️ Efectos fijos y controles", ficha.efectos_fijos_controles),
            ("💡 Mecanismos económicos", ficha.mecanismos),
            ("📊 Resultados", ficha.resultados),
            ("📚 Datos y muestra", ficha.datos_muestra),
            ("📝 Para tu trabajo", ficha.para_tu_trabajo),
        ]
    elif ficha.tipo == "tecnico":
        sections = [
            ("📌 Pregunta", ficha.pregunta),
            ("⚠️ El problema", ficha.el_problema),
            ("🧮 El argumento", ficha.el_argumento),
            ("🖼️ Ilustración empírica", ficha.ilustracion_empirica),
            ("📊 Qué cambia en la práctica", ficha.que_cambia_en_la_practica),
            ("🛠️ Qué usar en su lugar", ficha.que_usar_en_su_lugar),
            ("📝 Para tu trabajo", ficha.para_tu_trabajo),
        ]
    else:
        raise FichaError(f"Tipo de ficha desconocido: {ficha.tipo!r}")

    parts = [f"📄 <b>{escape_html(_format_titulo_autores(paper))}</b>"]

    if top_pick_reasoning:
        parts.append(f"🏆 <b>Por qué esta semana</b>\n{escape_html(top_pick_reasoning)}")

    for title, content in sections:
        parts.append(f"<b>{title}</b>\n{escape_html(content)}")

    parts.append(f"📖 <b>Referencia</b>\n{escape_html(_format_reference(paper))}")
    parts.append("📎 PDF adjunto")

    return "\n\n".join(parts)
