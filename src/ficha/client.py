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

## Campos de la ficha (en este orden, cada uno 1-4 oraciones, directo, sin relleno)

1. pregunta: que esta tratando de responder el paper.
2. contexto: lugar y anios del estudio (donde y cuando se recolectaron los datos \
o se dio el fenomeno estudiado, no el anio de publicacion).
3. metodo: etiqueta corta del estimador (ej. "DiD con Callaway-Sant'Anna", "RD \
con discontinuidad en edad", "VI con shock de oferta"). Una linea, no un parrafo.
4. identificacion: cual es el shock y cuales son las reglas de juego \
institucionales que generan la variacion que el paper explota. Explica COMO \
funciona la estrategia de identificacion, no solo repitas el nombre del metodo \
del punto anterior.
5. mecanismos: la teoria economica de por que deberia pasar lo que el paper \
predice o encuentra (el "por que", no el "que").
6. resultados: hallazgos principales, con la magnitud del efecto en unidades \
interpretables (puntos porcentuales, desviaciones estandar, pesos, anios de \
escolaridad, etc.) - nunca solo "el efecto es significativo".
7. datos_muestra: fuente de los datos y tamanio de la muestra (numero de \
observaciones, individuos, escuelas, municipios, segun aplique).
8. notas_extra: algo relevante sobre robustez, limites del estudio, o contexto \
que valga la pena mencionar y no entro en los puntos anteriores. Si no hay nada \
particularmente notable, un comentario breve y honesto (no inventes limitaciones \
solo por llenar el campo).

No repitas informacion entre campos. Escribe para un mensaje de WhatsApp: \
directo, sin relleno, sin frases como "en este paper los autores...". Ve al grano.\
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


def _format_reference(paper: Paper) -> str:
    authors = ", ".join(paper.authors) or "(autores desconocidos)"
    return f"{authors} ({paper.publication_year}). {paper.title}. {paper.journal}."


def format_ficha_message(ficha: FichaContent, paper: Paper) -> str:
    """Arma el texto final, listo para enviar por WhatsApp (Parte E adjunta el PDF aparte)."""
    sections = [
        ("1. Pregunta", ficha.pregunta),
        ("2. Contexto", ficha.contexto),
        ("3. Metodo", ficha.metodo),
        ("4. Identificacion", ficha.identificacion),
        ("5. Mecanismos economicos", ficha.mecanismos),
        ("6. Resultados", ficha.resultados),
        ("7. Datos y muestra", ficha.datos_muestra),
        ("8. Notas extra", ficha.notas_extra),
        ("9. Referencia", _format_reference(paper)),
    ]
    body = "\n\n".join(f"*{title}*\n{content}" for title, content in sections)
    return f"{body}\n\n*10.* 📎 PDF adjunto"
