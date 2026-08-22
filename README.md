# Sistema de papers académicos por WhatsApp

Pipeline que recibe automáticamente papers académicos relevantes por WhatsApp,
con resumen estructurado en español y PDF adjunto. Ver el spec completo para
el diseño de todas las partes (A–F).

Este repo también incluye un segundo pipeline, independiente pero pensado
para compartir el mismo canal de envío: **oportunidades académicas**
(fellowships pre-doctorales y posiciones de RA). Ver la sección
[Sistema de oportunidades académicas](#sistema-de-oportunidades-académicas-por-whatsapp)
más abajo.

## Estado actual: Partes A y B

**A — conexión con OpenAlex.** Conecta con la [API de OpenAlex](https://docs.openalex.org/)
y trae papers del top 40 de revistas de economía (por impacto, `2yr_mean_citedness`),
publicados en los últimos 10 años.

**B — filtro de relevancia + importancia.** Toma un lote de papers candidatos
(con abstract) y llama a la API de Claude para decidir cuáles son relevantes
para los temas prioritarios de la usuaria y cuál es el mejor candidato para
esa corrida, siguiendo la regla de selección del spec (importancia por encima
de recencia).

Todavía **no** resuelve el PDF con fallback a working paper (Parte C) ni
redacta la ficha final en español (Parte D).

### Estructura

```
src/openalex/
  journals.py   # Top 40 revistas, con su OpenAlex ID y peso por ranking
  client.py     # Cliente de la API de works de OpenAlex
src/relevance/
  client.py     # Filtro de relevancia + importancia con la API de Claude
scripts/
  fetch_test_papers.py         # Parte A: trae 5 papers de prueba y los imprime
  evaluate_relevance_test.py   # Parte B: trae papers recientes y los evalúa
  resolve_journals.py          # Utilidad para regenerar journals.py si cambia la lista de revistas
```

### Uso

```bash
pip install -r requirements.txt

# Parte A
OPENALEX_MAILTO=tu@email.com python scripts/fetch_test_papers.py

# Parte B (requiere además una API key de Claude)
OPENALEX_MAILTO=tu@email.com ANTHROPIC_API_KEY=sk-ant-... \
    python scripts/evaluate_relevance_test.py
```

`OPENALEX_MAILTO` es obligatorio: OpenAlex pide un email de contacto para
entrar en su "polite pool", que da límites de uso más altos y respuestas más
rápidas y confiables que las llamadas anónimas.

`ANTHROPIC_API_KEY` es la API key de la [API de Claude](https://platform.claude.com/)
(distinta de cualquier login de Claude Code) — necesaria para la Parte B en
adelante. Por defecto el filtro usa `claude-opus-5`; se puede pasar un modelo
más económico (p. ej. `claude-sonnet-5`) al llamar `evaluate_papers(..., model=...)`
si el costo es una preocupación, dado que clasificar abstracts es una tarea
relativamente simple.

### Cómo se armó el top 40

La lista de revistas (`src/openalex/journals.py`) se resolvió una sola vez
contra la API de OpenAlex por ISSN (top-5 de economía + revistas de campo
ampliamente reconocidas en población/juventud, género, salud, educación e
inferencia causal), y se ordenó por `summary_stats.2yr_mean_citedness` como
proxy de impacto. Los IDs quedan hardcodeados para no gastar cuota de la API
resolviéndolos en cada corrida del pipeline. Para regenerar la lista (ajustar
qué revistas entran, o refrescar el ranking de impacto), correr
`scripts/resolve_journals.py` y pegar su salida en `journals.py`.

### Notas / limitaciones conocidas

- Algunas revistas (p. ej. Elsevier — Journal of Econometrics) no entregan
  abstract a través de OpenAlex; el campo queda vacío para esos papers.
- No todos los papers tienen versión de acceso abierto vía OpenAlex, incluso
  papers muy citados (ej. Goodman-Bacon 2021 sobre DiD con tratamiento
  escalonado). Ese es exactamente el caso que la Parte C debe resolver con
  fallback a NBER/IZA/SSRN/página del autor.

### Próximos pasos (spec)

- **C.** Consecución del PDF (OpenAlex/Unpaywall + fallback a working paper).
- **D.** Generación de la ficha estructurada en español con la API de Claude.
- **E.** Envío por WhatsApp (Twilio o Meta Cloud API).
- **F.** Automatización (cron / GitHub Actions), 2–3 veces por semana.

---

## Sistema de oportunidades académicas por WhatsApp

Pipeline paralelo al de papers: recibe automáticamente por WhatsApp
fellowships pre-doctorales y posiciones de research assistant (RA) que
encajen con los intereses de la usuaria, en la misma ficha fija de siempre.

Cubre dos tracks, ambos en economía con foco en educación:

- **Académico:** fellowship pre-doctoral o RA, en cualquier universidad,
  con foco en profesores/labs que trabajan en educación en países de
  middle income (ej. Uganda, Colombia) — ver el ejemplo de referencia abajo.
- **Entidades multilaterales / gubernamentales de desarrollo:** research
  analyst, research assistant, consultant de investigación, o programas de
  young professionals (ej. WBG YPP, IADB YPP) en Banco Mundial, BID/IADB,
  CAF, OCDE, UNESCO, UNICEF y organismos análogos, en el área de economía
  de la educación.

No existe un equivalente a OpenAlex para este tipo de oportunidades (no hay
una base de datos única y estructurada de fellowships/RA), así que este
pipeline usa la API de Claude con sus herramientas de búsqueda (`web_search`)
y de lectura de páginas (`web_fetch`) en vez de un cliente a una API externa.

### Estructura

```
src/opportunities/
  discovery.py  # Parte A: busca candidatos en la web (web_search)
  extract.py    # Parte B: verifica cada candidato (web_fetch) y arma la ficha
  format.py     # Arma el mensaje de WhatsApp con la ficha fija
  store.py      # Evita reenviar una oportunidad ya notificada en corridas previas
scripts/
  discover_test_opportunities.py  # Parte A: prueba solo el descubrimiento
  run_opportunities_test.py       # Corrida completa: descubre + verifica + arma ficha
```

### Ficha (formato fijo del mensaje)

1. 🎓 Posición — tipo y nombre exacto
2. 🏛️ Institución — universidad y profesor/lab a cargo
3. 📍 Foco temático
4. 🌍 Países involucrados
5. 💰 Salario/financiamiento
6. 📅 Fecha límite (o "no especificada")
7. ✅ Requisitos clave
8. 🔗 Link para aplicar

### Ejemplos de referencia

No son un filtro literal — son el patrón a reconocer en otras
universidades/labs/organismos.

- **Académico:** Embedded Development Lab (Harvard Graduate School of
  Education), bajo el profesor Vesall Nourani: fellowship pre-doctoral con
  foco en formación docente en Uganda y en la evaluación del programa
  educativo SAT de FUNDAEC en Colombia.
- **Multilateral:** Research Analyst / Consultant en el equipo de
  Educación del Banco Mundial (Education Global Practice) o del BID
  (División de Educación), apoyando evaluaciones de impacto y análisis
  cuantitativo de política educativa en países en desarrollo.

### Uso

```bash
pip install -r requirements.txt

# Solo descubrimiento (Parte A)
ANTHROPIC_API_KEY=sk-ant-... python scripts/discover_test_opportunities.py

# Corrida completa: descubre, verifica y muestra los mensajes de WhatsApp
ANTHROPIC_API_KEY=sk-ant-... python scripts/run_opportunities_test.py
```

Cada corrida guarda en `data/opportunities_seen.json` (no versionado) los
links ya notificados, para no repetir la misma oportunidad en la siguiente
corrida mientras siga abierta.

### Limitaciones conocidas / próximos pasos

- La cobertura depende de qué tan bien indexadas estén las páginas de los
  labs/profesores en los motores de búsqueda que usa `web_search`; no hay
  garantía de encontrar el 100% de las convocatorias abiertas.
- Todavía no envía nada por WhatsApp: eso es la Parte E, compartida con el
  pipeline de papers (Twilio o Meta Cloud API), y la Parte F de
  automatización (cron / GitHub Actions) tampoco está implementada.
