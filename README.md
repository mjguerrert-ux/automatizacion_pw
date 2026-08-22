# Sistema de papers académicos por WhatsApp

Pipeline que recibe automáticamente papers académicos relevantes por WhatsApp,
con resumen estructurado en español y PDF adjunto. Ver el spec completo para
el diseño de todas las partes (A–F).

## Estado actual: Partes A, B, C y D

**A — conexión con OpenAlex.** Conecta con la [API de OpenAlex](https://docs.openalex.org/)
y trae papers del top 40 de revistas de economía (por impacto, `2yr_mean_citedness`),
publicados en los últimos 10 años.

**B — filtro de relevancia + importancia.** Toma un lote de papers candidatos
(con abstract) y llama a la API de Claude para decidir cuáles son relevantes
para los temas prioritarios de la usuaria y cuál es el mejor candidato para
esa corrida, siguiendo la regla de selección del spec (importancia por encima
de recencia).

**C — consecución del PDF.** Para un paper dado, intenta conseguir el PDF
completo en este orden: URL de acceso abierto de OpenAlex → Unpaywall (por
DOI) → ubicaciones alternativas que ya trae OpenAlex apuntando a NBER/IZA/
SSRN/RePEc/EconStor → si nada de eso funciona, le pide a la API de Claude
(con su herramienta de búsqueda web) que encuentre la versión de working
paper y descarga esa URL. Cada candidato se valida como PDF real (no solo
que responda 200) antes de darlo por bueno.

**D — generación de la ficha.** Con el PDF ya descargado (Parte C), le pasa el
PDF completo a la API de Claude (como documento, no como texto extraído) y le
pide que llene los primeros 8 campos de la ficha del spec (pregunta, contexto,
método, identificación, mecanismos, resultados, datos y muestra, notas extra),
en español y calibrada al contexto de la usuaria. La referencia completa (9) se
arma con los metadatos de OpenAlex, no con lo que transcriba el modelo, para
que la cita sea siempre exacta.

Todavía **no** envía nada por WhatsApp (Parte E) ni corre solo (Parte F).

### Estructura

```
src/openalex/
  journals.py   # Top 40 revistas, con su OpenAlex ID y peso por ranking
  client.py     # Cliente de la API de works de OpenAlex
src/relevance/
  client.py     # Filtro de relevancia + importancia con la API de Claude
src/pdf/
  client.py     # Consecución del PDF: OA → Unpaywall → repos conocidos → búsqueda web
src/ficha/
  client.py     # Genera la ficha leyendo el PDF completo con la API de Claude
scripts/
  fetch_test_papers.py         # Parte A: trae 5 papers de prueba y los imprime
  evaluate_relevance_test.py   # Parte B: trae papers recientes y los evalúa
  resolve_pdf_test.py          # Parte C: A + B, y descarga el PDF del top pick
  generate_ficha_test.py       # Parte D: A + B + C, y genera + imprime la ficha final
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

# Parte C (encadena A + B, y descarga el PDF del top pick a .pdf_downloads/)
OPENALEX_MAILTO=tu@email.com ANTHROPIC_API_KEY=sk-ant-... \
    python scripts/resolve_pdf_test.py

# Parte D (encadena A + B + C, e imprime la ficha final)
OPENALEX_MAILTO=tu@email.com ANTHROPIC_API_KEY=sk-ant-... \
    python scripts/generate_ficha_test.py
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
  escalonado). Probado en la práctica: el fallback de la Parte C encontró y
  descargó la versión NBER de ese mismo paper sin intervención manual.
- OpenAlex cambió a un modelo con una cuota diaria gratis limitada por API key/
  contacto (antes era ilimitado); si el pipeline empieza a fallar con
  `Rate limit exceeded / Insufficient budget`, hay que esperar al reset (medianoche
  UTC) o conseguir una cuota mayor. Con 2–3 corridas/semana y pocas llamadas
  por corrida no debería ser un problema en producción.
- Algunas editoriales (Oxford University Press, SSRN) devuelven 403 a
  descargas automatizadas desde IPs de datacenter, aunque la URL sea pública.
  Cuando pasa, `resolve_pdf` sigue probando el resto de la cascada de fuentes;
  si ninguna funciona, devuelve la URL encontrada igual (para referencia)
  pero sin archivo descargado.
- La ficha que genera la Parte D es técnicamente muy precisa (magnitudes
  exactas, mecanismo de sesgo, conexión con proyectos activos de la usuaria),
  pero cada campo puede salir bastante largo para un mensaje de WhatsApp —
  sobre todo en papers metodológicos densos. Si en la práctica resulta
  demasiado largo, hay que ajustar `SYSTEM_PROMPT` en `src/ficha/client.py`
  para acortar campos específicos (ej. limitar "identificación" y
  "resultados" a 2-3 oraciones en vez de dejarlo abierto).

### Próximos pasos (spec)

- **E.** Envío por WhatsApp (Twilio o Meta Cloud API).
- **F.** Automatización (cron / GitHub Actions), 2–3 veces por semana.
