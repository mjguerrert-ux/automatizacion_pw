# Sistema de papers académicos por WhatsApp

Pipeline que recibe automáticamente papers académicos relevantes por WhatsApp,
con resumen estructurado en español y PDF adjunto. Ver el spec completo para
el diseño de todas las partes (A–F).

## Estado actual: Parte A — conexión con OpenAlex

Lo que hay hasta ahora conecta con la [API de OpenAlex](https://docs.openalex.org/)
y trae papers del top 40 de revistas de economía (por impacto, `2yr_mean_citedness`),
publicados en los últimos 10 años. Todavía **no** filtra por tema/relevancia
(eso es la Parte B) ni resuelve el PDF con fallback a working paper (Parte C).

### Estructura

```
src/openalex/
  journals.py   # Top 40 revistas, con su OpenAlex ID y peso por ranking
  client.py     # Cliente de la API de works de OpenAlex
scripts/
  fetch_test_papers.py   # Parte A: trae 5 papers de prueba y los imprime
  resolve_journals.py    # Utilidad para regenerar journals.py si cambia la lista de revistas
```

### Uso

```bash
pip install -r requirements.txt
OPENALEX_MAILTO=tu@email.com python scripts/fetch_test_papers.py
```

`OPENALEX_MAILTO` es obligatorio: OpenAlex pide un email de contacto para
entrar en su "polite pool", que da límites de uso más altos y respuestas más
rápidas y confiables que las llamadas anónimas.

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

- **B.** Filtro de relevancia + importancia con la API de Claude sobre abstracts.
- **C.** Consecución del PDF (OpenAlex/Unpaywall + fallback a working paper).
- **D.** Generación de la ficha estructurada en español con la API de Claude.
- **E.** Envío por WhatsApp (Twilio o Meta Cloud API).
- **F.** Automatización (cron / GitHub Actions), 2–3 veces por semana.
