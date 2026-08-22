"""
Parte D: generacion de la ficha estructurada en espanol, leyendo el PDF
completo del paper con la API de Claude.

La ficha sigue el orden fijo del spec:
1. Pregunta 2. Contexto 3. Metodo 4. Identificacion 5. Mecanismos economicos
6. Resultados 7. Datos y muestra 8. Notas extra 9. Referencia completa
10. PDF adjunto

Los primeros 8 campos los llena Claude leyendo el PDF; la referencia (9) se
arma con los metadatos que ya tenemos de OpenAlex (Parte A), para que la cita
sea exacta y no dependa de que el modelo la transcriba bien. El punto 10 no
es contenido generado: es el archivo que Parte E adjunta al mensaje.
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from pathlib import Path

import anthropic

from openalex.client import Paper

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

## Campos de la ficha (en este orden). Vas a mandar esto por Telegram: Telegram \
corta mensajes de mas de 4096 caracteres, y esta ficha comparte el mensaje con \
un encabezado y una referencia. Cada limite de palabras de abajo es un TECHO \
DURO, no una sugerencia - contalas antes de responder. El limite es de palabras, \
no de oraciones: NO cumplas el limite escribiendo una sola oracion larguisima \
llena de comas, guiones y parentesis. Si el paper tiene mucho detalle tecnico \
(formulas, muchas especificaciones alternativas, varios tests), tenes que \
CORTAR contenido, no comprimir la sintaxis para que quepa todo. Ante la duda \
entre completitud y brevedad, elegi brevedad: mejor transmitir la idea central \
con precision que enumerar cada detalle del paper. Quedan cosas afuera - esta \
bien, es una ficha de una pagina, no una resenia completa.

1. pregunta (25 palabras maximo): que esta tratando de responder el paper.
2. contexto (25 palabras maximo): lugar y anios del estudio (donde y cuando se \
recolectaron los datos o se dio el fenomeno estudiado, no el anio de publicacion).
3. metodo (12 palabras maximo, etiqueta corta - NO una oracion completa): ej. \
"DiD con Callaway-Sant'Anna", "RD con discontinuidad en edad", "VI con shock de \
oferta". Si el paper es puramente metodologico/diagnostico (no aplica el metodo \
a un fenomeno sustantivo, como una descomposicion de otro estimador), \
etiquetalo como tal, ej. "Diagnostico algebraico de TWFE", no lo redactes como \
si fuera una aplicacion empirica.
4. identificacion (60 palabras maximo): cual es el shock y cuales son las \
reglas de juego institucionales que generan la variacion que el paper explota. \
Explica COMO funciona la estrategia de identificacion (el mecanismo tecnico/ \
institucional) en terminos generales - NO derives formulas, NO enumeres cada \
termino de una descomposicion, NO description paso a paso de un test \
estadistico. Si el paper es puramente algebraico/metodologico sin un shock \
institucional real, dilo en una frase ("no hay un shock nuevo: el aporte es...") \
en vez de forzar una identificacion que no existe.
5. mecanismos (35 palabras maximo): la teoria economica de por que deberia \
pasar lo que el paper predice o encuentra - el "por que" normativo/teorico, NO \
el "como" tecnico (eso ya esta en identificacion). Si ya explicaste en \
identificacion que un sesgo viene de tal mecanica, aca NO la vuelvas a describir: \
anda directo a la razon economica de fondo (ej. seleccion, incentivos, \
comportamiento optimizador), sin repetir el mecanismo algebraico/institucional \
del punto 4.
6. resultados (60 palabras maximo): el hallazgo principal, con la magnitud del \
efecto en unidades interpretables (puntos porcentuales, desviaciones estandar, \
pesos, anios de escolaridad, etc.) - nunca solo "el efecto es significativo". \
Si hay muchas especificaciones alternativas o una tabla larga de robustez, da \
SOLO el rango (ej. "las especificaciones alternativas van de X a Y") sin \
nombrar cada una ni sus valores individuales.
7. datos_muestra (20 palabras maximo): fuente de los datos y tamanio de la \
muestra (numero de observaciones, individuos, escuelas, municipios, segun \
aplique).
8. notas_extra (35 palabras maximo): prioriza SIEMPRE una conexion concreta y \
especifica con el trabajo activo de la usuaria si el paper aplica - no te \
limites a nombrar el programa (PAE, PEEP, desercion, salud mental, \
anticoncepcion de emergencia, capital humano), di especificamente que deberia \
revisar o tener en cuenta en SU analisis por este paper. Si nada del paper \
conecta con su trabajo, entonces si comenta robustez o limites del estudio. No \
inventes limitaciones solo por llenar el campo.

Los campos NUNCA se repiten entre si - cada uno tiene un trabajo distinto, no \
te salgas de el (ver especialmente identificacion vs. mecanismos arriba). \
Escribe para un mensaje de chat: directo, sin relleno, sin frases como "en \
este paper los autores...". Ve al grano.\
"""

_FICHA_SCHEMA = {
    "type": "object",
    "properties": {
        "pregunta": {"type": "string"},
        "contexto": {"type": "string"},
        "metodo": {"type": "string"},
        "identificacion": {"type": "string"},
        "mecanismos": {"type": "string"},
        "resultados": {"type": "string"},
        "datos_muestra": {"type": "string"},
        "notas_extra": {"type": "string"},
    },
    "required": [
        "pregunta",
        "contexto",
        "metodo",
        "identificacion",
        "mecanismos",
        "resultados",
        "datos_muestra",
        "notas_extra",
    ],
    "additionalProperties": False,
}


class FichaError(RuntimeError):
    pass


@dataclass
class FichaContent:
    pregunta: str
    contexto: str
    metodo: str
    identificacion: str
    mecanismos: str
    resultados: str
    datos_muestra: str
    notas_extra: str


def generate_ficha(
    paper: Paper,
    pdf_path: str,
    model: str = DEFAULT_MODEL,
    effort: str = "high",
    api_key: str | None = None,
) -> FichaContent:
    """Lee el PDF completo y llena los primeros 8 campos de la ficha.

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


def format_ficha_message(
    ficha: FichaContent,
    paper: Paper,
    top_pick_reasoning: str | None = None,
) -> str:
    """Arma el texto final, listo para enviar por Telegram (Parte E adjunta el PDF aparte).

    `top_pick_reasoning` es la razon (de la Parte B) de por que este paper se
    eligio sobre los demas candidatos de la corrida - sin esto, la usuaria
    recibe la ficha sin saber por que le llego justo este paper.
    """
    sections = [
        ("1. ❓ Pregunta", ficha.pregunta),
        ("2. 📍 Contexto", ficha.contexto),
        ("3. 🔬 Método", ficha.metodo),
        ("4. 🎯 Identificación", ficha.identificacion),
        ("5. ⚙️ Mecanismos económicos", ficha.mecanismos),
        ("6. 📊 Resultados", ficha.resultados),
        ("7. 🗂️ Datos y muestra", ficha.datos_muestra),
        ("8. 📝 Notas extra", ficha.notas_extra),
        ("9. 📚 Referencia", _format_reference(paper)),
    ]
    body = "\n\n".join(f"*{title}*\n{content}" for title, content in sections)

    header = ""
    if top_pick_reasoning:
        header = f"*🏆 Por qué esta semana*\n{top_pick_reasoning}\n\n"

    return f"{header}{body}\n\n*10.* 📎 PDF adjunto"
