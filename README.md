# Sistema de papers académicos por WhatsApp

Pipeline que recibe automáticamente papers académicos relevantes, con
resumen estructurado en español y PDF adjunto. Ver el spec completo para
el diseño de todas las partes (A–F).

> **Nota sobre el canal de envío:** el nombre del proyecto dice "por
> WhatsApp" (la idea original), pero el envío automático implementado
> (Parte E, ver abajo) usa **Telegram** — WhatsApp exige verificación de
> negocio en Meta y una plantilla pre-aprobada para cualquier mensaje
> automático, incluso mandándote notificaciones a vos misma, lo cual es
> desproporcionado para un sistema de notificación personal. Telegram
> cumple el mismo objetivo (llega al celular, automático) sin esa fricción.

Este repo también incluye un segundo pipeline, independiente pero pensado
para compartir el mismo canal de envío: **oportunidades académicas**
(fellowships pre-doctorales y posiciones de RA). Ver la sección
[Sistema de oportunidades académicas](#sistema-de-oportunidades-académicas)
más abajo.

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

El envío por Telegram (Parte E) ya está implementado y en uso por el
pipeline de oportunidades (ver [más abajo](#envío-por-telegram-parte-e)) —
falta conectarlo a este pipeline de papers, y agregar la Parte F
(automatización vía GitHub Actions, análoga a la que ya corre para
oportunidades).

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
  pero cada campo puede salir bastante largo para un mensaje de chat —
  sobre todo en papers metodológicos densos. Si en la práctica resulta
  demasiado largo, hay que ajustar `SYSTEM_PROMPT` en `src/ficha/client.py`
  para acortar campos específicos (ej. limitar "identificación" y
  "resultados" a 2-3 oraciones en vez de dejarlo abierto).

### Próximos pasos (spec)

- **E.** Conectar este pipeline al envío por Telegram — el módulo
  (`src/telegram/`) ya existe y está en uso por el pipeline de
  oportunidades (ver abajo); falta un script que encadene A→B→C→D→envío.
- **F.** Automatización vía GitHub Actions, 2–3 veces por semana — análoga
  a `.github/workflows/opportunities.yml`, pero para este pipeline.

---

## Sistema de oportunidades académicas

Pipeline paralelo al de papers: recibe automáticamente por Telegram
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
  format.py     # Arma el mensaje con la ficha fija
  store.py      # Evita reenviar una oportunidad ya notificada en corridas previas
src/telegram/
  client.py     # Parte E: envío por Telegram vía un bot personal (compartido con papers)
scripts/
  discover_test_opportunities.py  # Parte A: prueba solo el descubrimiento
  run_opportunities_test.py       # Corrida de prueba: descubre + verifica + imprime la ficha (no envía)
  send_opportunities.py           # Corrida real: descubre + verifica + ENVÍA por Telegram
  send_test_telegram.py           # Prueba de humo del bot, compartida con el pipeline de papers
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

# Corrida de prueba: descubre, verifica y solo IMPRIME los mensajes (no envía)
ANTHROPIC_API_KEY=sk-ant-... python scripts/run_opportunities_test.py

# Corrida real: descubre, verifica y ENVÍA por Telegram cada oportunidad nueva
ANTHROPIC_API_KEY=sk-ant-... \
    TELEGRAM_BOT_TOKEN=123456789:ABC-... TELEGRAM_CHAT_ID=... \
    python scripts/send_opportunities.py
```

Cada corrida guarda en `data/opportunities_seen.json` (no versionado) los
links ya notificados/enviados, para no repetir la misma oportunidad en la
siguiente corrida mientras siga abierta. `send_opportunities.py` solo marca
una oportunidad como vista después de que el envío por Telegram fue exitoso;
si falla, se reintenta en la próxima corrida.

### Limitaciones conocidas

- La cobertura depende de qué tan bien indexadas estén las páginas de los
  labs/profesores/organismos en los motores de búsqueda que usa `web_search`;
  no hay garantía de encontrar el 100% de las convocatorias abiertas.

---

## Envío por Telegram (Parte E)

Módulo compartido por ambos pipelines (`src/telegram/client.py`), vía la
[API de bots de Telegram](https://core.telegram.org/bots/api#sendmessage).
Se eligió Telegram en vez de WhatsApp Business porque WhatsApp exige
verificación de negocio en Meta y una plantilla pre-aprobada para *cualquier*
mensaje que el sistema inicie sin que la usuaria haya escrito antes —
desproporcionado para notificarse a una sola persona. Un bot de Telegram
manda mensajes libremente desde el minuto uno, sin aprobación de nadie.

**Setup (una sola vez, ~2 minutos):**
1. En Telegram, buscar **@BotFather** y mandarle `/newbot`. Seguir las
   instrucciones (nombre + username del bot). Da un **token**, formato
   `123456789:ABC-...`.
2. Buscar tu bot nuevo por el username que le pusiste y mandarle cualquier
   mensaje (ej. "hola") — un bot no puede escribirle primero a un chat que
   nunca le escribió.
3. Abrir en el navegador `https://api.telegram.org/bot<TOKEN>/getUpdates`
   (con tu token) y copiar tu **chat_id** de `result[0].message.chat.id`.

```bash
# Prueba de humo: manda un mensaje de texto suelto
TELEGRAM_BOT_TOKEN=123456789:ABC-... TELEGRAM_CHAT_ID=... \
    python scripts/send_test_telegram.py
```

### Variables de entorno

| Variable | Obligatoria | Descripción |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | sí | Token del bot, dado por @BotFather (paso 1). |
| `TELEGRAM_CHAT_ID` | sí | chat_id destino (paso 3). |

**Límite:** Telegram permite hasta 4096 caracteres por mensaje;
`send_telegram_message` levanta `TelegramError` si lo supera (las fichas de
oportunidades caben cómodamente dentro de ese límite; las de papers, ver
nota de longitud en la sección de arriba, hay que vigilarlas).

---

## Automatización (Parte F)

El pipeline de oportunidades corre solo, sin intervención manual, vía
GitHub Actions: `.github/workflows/opportunities.yml` ejecuta
`scripts/send_opportunities.py` **lunes, miércoles y viernes a las 8:00am
hora Colombia**.

**Setup (una sola vez), en la página del repo en GitHub:**
1. Completar el setup de Telegram de la sección anterior (bot + chat_id).
2. Settings → Secrets and variables → Actions → New repository secret, y
   agregar: `ANTHROPIC_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.
3. Mergear la rama con este workflow a la rama default del repo (`main`) —
   los triggers de horario (`schedule`) de GitHub Actions **solo** se activan
   con la versión del workflow que está en la rama default, no en una rama
   feature. Sin este paso el cron queda inactivo aunque el archivo ya exista.

**Para probarlo sin esperar al cron:** pestaña Actions del repo →
"Oportunidades académicas por Telegram" → Run workflow (dispara el
`workflow_dispatch`, que sí funciona desde cualquier rama que tenga el
archivo).

**Cómo persiste el estado entre corridas:** cada corrida del workflow parte
de un checkout limpio (no hay disco persistente en GitHub Actions), así que
`data/opportunities_seen.json` se guarda/restaura con `actions/cache` en vez
de comprometerlo al repo — evita tanto perder el historial de oportunidades
ya enviadas como llenar el repo de commits automáticos.

**Costo a tener en cuenta:** cada corrida hace llamados reales a la API de
Claude (con `web_search`/`web_fetch`); Telegram en sí es gratis. El volumen
de 3 corridas/semana es bajo, pero no deja de costar por el lado de Claude.

### Pendiente

- El pipeline de papers (Partes A–D, ya completas) no está conectado a
  ningún workflow todavía — falta un job análogo a este mismo archivo (o uno
  separado, `papers.yml`) que encadene A→B→C→D y envíe por `src/telegram/`.
