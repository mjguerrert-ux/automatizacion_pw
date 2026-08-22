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

## Estado actual: Partes A–F completas

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
pide que llene una ficha en español, calibrada al contexto de la usuaria. Hay
**dos plantillas** — Claude elige cuál usar después de leer el paper completo
(campo `tipo`), porque un solo formato no le sirve igual a un paper aplicado
que a uno puramente metodológico:

- **Aplicado** (responde una pregunta sustantiva con un método): Pregunta,
  Contexto, Método, Identificación, Efectos fijos y controles, Mecanismos
  económicos, Resultados, Datos y muestra.
- **Técnico/metodológico** (propone o diagnostica un estimador en sí mismo):
  Pregunta, El problema, El argumento, Ilustración empírica (breve,
  secundaria), Qué cambia en la práctica, Qué usar en su lugar.

Título/autores y Referencia se arman con los metadatos de OpenAlex, no con lo
que transcriba el modelo, para que la cita sea siempre exacta. No hay un
campo de "para tu trabajo": ese espacio se le dio a los campos conceptuales
para que expliquen mejor la idea central, en vez de gastar palabras
conectando con proyectos activos de la usuaria — eso ahora se resuelve
preguntando directamente (ver Parte E).

Las secciones más conceptuales (Identificación, Efectos fijos y controles,
Mecanismos, Resultados / El problema, El argumento, Qué cambia en la
práctica) tienen presupuestos de palabras generosos y una instrucción
explícita de desarrollar la lógica paso a paso, no solo nombrar el
concepto — el criterio es "¿alguien que no escribió el paper entendería
esto, o solo se entera de que existe?". Efectos fijos y controles además se
redacta como una **lista** (un bullet por cada efecto fijo/control, cada uno
explicando la intuición económica de por qué hace falta), no como un
párrafo. Para que esto quepa sin volver a pelear con el límite de 4096
caracteres de Telegram, `format_ficha_message` manda la ficha en **dos
mensajes** en vez de uno: el primero hasta Efectos fijos y controles (o
Ilustración empírica en la técnica), el segundo con el resto + la
referencia.

**E — envío por Telegram + preguntas de seguimiento.** Manda la ficha (dos
mensajes de texto, con `parse_mode="HTML"` para que la negrita se vea de
verdad — Telegram no renderiza formato si no se lo pedís explícitamente) y
el PDF (documento adjunto) por un bot de Telegram **separado** del pipeline
de oportunidades — son dos chats distintos que no se mezclan.

Además, la usuaria puede escribirle preguntas puntuales al bot sobre el
**último paper enviado** y recibe una respuesta generada releyendo el PDF
completo (sin memoria conversacional entre preguntas distintas, por ahora).
Como no hay un servidor escuchando en tiempo real, esto funciona por
*polling*: justo después de mandar un paper, `send_papers.py` revisa cada
10 segundos por 10 minutos (la mayoría de las preguntas llegan poco después
de la notificación); pasada esa ventana, un workflow aparte
(`papers_qa.yml`, cada 5 minutos) sigue cubriendo el resto del día/semana.
Ver [Envío por Telegram](#envío-por-telegram-parte-e) más abajo para el
detalle compartido con oportunidades, y la sección de variables de entorno
para el bot específico de papers.

**F — automatización.** `.github/workflows/papers.yml` corre
`scripts/send_papers.py` solo, **lunes, martes y jueves a las 7:00am hora
Colombia** — horario distinto al del pipeline de oportunidades (lun/mié/vie
1pm), para que no lleguen los dos mensajes el mismo momento (ese job queda
corriendo ~10 minutos extra al final, por la ráfaga de preguntas descrita
arriba). Guarda en `data/` (vía cache de Actions, igual que oportunidades)
los `openalex_id` ya enviados y el paper "actual" para las preguntas de
seguimiento, para no repetir el mismo paper si sigue siendo el "top pick"
en una corrida futura.

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
src/papers/
  store.py      # Evita reenviar un paper ya notificado en corridas previas
  qa_state.py   # Estado del "paper actual" (para las preguntas) y el offset de Telegram
  qa.py         # Responde una pregunta puntual releyendo el PDF del paper actual
  qa_poll.py    # Logica compartida de "revisar y responder" (rafaga y poll de fondo)
scripts/
  fetch_test_papers.py         # Parte A: trae 5 papers de prueba y los imprime
  evaluate_relevance_test.py   # Parte B: trae papers recientes y los evalúa
  resolve_pdf_test.py          # Parte C: A + B, y descarga el PDF del top pick
  generate_ficha_test.py       # Parte D: A + B + C, e imprime la ficha final (no envía)
  send_papers.py               # Parte E+F: A→B→C→D, ENVÍA por Telegram y hace la ráfaga de preguntas
  answer_paper_questions.py    # Poll de fondo (cada 5 min) de preguntas de seguimiento
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

# Parte D (encadena A + B + C, e imprime la ficha final, no envía nada)
OPENALEX_MAILTO=tu@email.com ANTHROPIC_API_KEY=sk-ant-... \
    python scripts/generate_ficha_test.py

# Parte E+F (encadena A→B→C→D y ENVÍA por Telegram - uso real)
OPENALEX_MAILTO=tu@email.com ANTHROPIC_API_KEY=sk-ant-... \
    TELEGRAM_BOT_TOKEN_PAPERS=123456789:ABC-... TELEGRAM_CHAT_ID_PAPERS=... \
    python scripts/send_papers.py
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
- El `SYSTEM_PROMPT` de la Parte D pone un techo duro de **palabras** (no de
  oraciones) por campo — un límite por oraciones no funciona: el modelo lo
  cumple igual escribiendo una sola oración larguísima con comas y guiones,
  sin bajar el largo real del mensaje. La ficha se manda en **dos mensajes**
  de Telegram (no uno), lo que da margen de sobra para que las secciones
  conceptuales sean genuinamente explicativas sin acercarse al límite de
  4096 caracteres por mensaje — probado con Duflo (2001): 2444 y 1692
  caracteres (60% y 41% del límite) pese al contenido mucho más detallado
  que las primeras versiones. Si en la práctica algún mensaje se acerca al
  límite, hay que bajar los topes de palabras en `src/ficha/client.py`
  (nunca volver a un límite por oraciones) o repartir las secciones en más
  de dos mensajes.

Con esto, el pipeline de papers ya cubre las 6 partes del spec (A–F).

---

## Sistema de oportunidades académicas

Pipeline paralelo al de papers: recibe automáticamente por Telegram
fellowships pre-doctorales y posiciones de research assistant (RA) que
encajen con los intereses de la usuaria, en la misma ficha fija de siempre.

Cubre dos tracks, ambos en economía con foco en educación:

- **Académico:** fellowship pre-doctoral o RA, en cualquier universidad
  (sin filtro geográfico — puede ser top de EEUU/Europa, como el ejemplo
  de referencia), con foco en profesores/labs que trabajan en educación.
- **Entidades multilaterales / gubernamentales de desarrollo:** research
  analyst, research assistant, consultant de investigación, o programas de
  young professionals (ej. WBG YPP, IADB YPP) en Banco Mundial, BID/IADB,
  CAF, OCDE, UNESCO, UNICEF y organismos análogos, en el área de economía
  de la educación.

**"Middle income" es sobre a quién prioriza el programa, no sobre el tema
de investigación.** La usuaria vive en Colombia, así que el pipeline
destaca (sin excluir al resto) las oportunidades que dan preferencia
explícita a candidatos de países de middle income/en desarrollo — igual
que el ejemplo de referencia: lo que lo hace relevante no es que investigue
*sobre* Uganda/Colombia, es que el programa prioriza candidatos *de* esos
países. La mayoría de fellowships de RA/pre-doc no lo dicen explícitamente
y siguen siendo relevantes igual; cuando el pipeline encuentra esa señal,
la deja en el campo de foco temático de la ficha.

**Solo fuentes oficiales.** Cada oportunidad tiene que venir de la página
oficial de la universidad/lab o del organismo — nunca de una bolsa de
empleo/agregador (LinkedIn, Indeed, econjobmarket, predoc.org, etc., ver
`BLOCKED_JOB_BOARD_DOMAINS` en `discovery.py`). Un agregador puede servir
para *encontrar* una oportunidad, pero el `apply_link` final siempre tiene
que resolver a la página oficial de la convocatoria.

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
  Education), bajo el profesor Vesall Nourani: fellowship pre-doctoral de
  educación que, según la usuaria, da prioridad a candidatos de países de
  middle income — por eso le interesa particularmente a ella, que vive en
  Colombia.
- **Multilateral:** Research Analyst / Consultant en el equipo de
  Educación del Banco Mundial (Education Global Practice) o del BID
  (División de Educación) — este tipo de organismos frecuentemente buscan
  diversidad geográfica y dan preferencia a candidatos de sus países
  miembro en desarrollo.

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

### Costo

Por defecto usa `claude-sonnet-5` con `effort="medium"` en ambas partes (A
y B) — más barato que `claude-opus-5`/"high", suficiente para una tarea de
búsqueda + clasificación/extracción (no necesita el modelo más caro). La
Parte B además limita cuánto contenido de cada página se ingiere
(`MAX_FETCH_CONTENT_TOKENS`, 6000 tokens) y bloquea los agregadores de
empleo de las búsquedas — el mayor costo real es leer páginas completas
con `web_fetch`, así que topearlo ayuda tanto al costo como a la
relevancia. Si ves candidatos o fichas de baja calidad, se puede subir a
`claude-opus-5`/"high" pasando `model=`/`effort=` a `discover_opportunities`
o `extract_fichas`.

### Limitaciones conocidas

- La cobertura depende de qué tan bien indexadas estén las páginas de los
  labs/profesores/organismos en los motores de búsqueda que usa `web_search`;
  no hay garantía de encontrar el 100% de las convocatorias abiertas.
- La Parte B (`extract_fichas`) verifica en lotes de 8 candidatos por
  llamada (`batch_size`), no todos a la vez: con muchos candidatos en un
  solo turno, Claude puede cortarlo a mitad de camino (`pause_turn`) antes
  de devolver el resultado — pasó en la corrida real del 22/08 con 42
  candidatos. Si un lote entero falla, se descarta ese lote (sus
  candidatos se reintentan solos en la próxima corrida) en vez de abortar
  toda la corrida.

---

## Envío por Telegram (Parte E)

Módulo compartido por ambos pipelines (`src/telegram/client.py`), vía la
[API de bots de Telegram](https://core.telegram.org/bots/api#sendmessage).
Se eligió Telegram en vez de WhatsApp Business porque WhatsApp exige
verificación de negocio en Meta y una plantilla pre-aprobada para *cualquier*
mensaje que el sistema inicie sin que la usuaria haya escrito antes —
desproporcionado para notificarse a una sola persona. Un bot de Telegram
manda mensajes libremente desde el minuto uno, sin aprobación de nadie.

**Papers y oportunidades usan bots (y chats) separados** — son notificaciones
de naturaleza distinta y no deben mezclarse en la misma conversación. Repetir
el setup de abajo dos veces, una por pipeline.

**Setup (una sola vez por bot, ~2 minutos):**
1. En Telegram, buscar **@BotFather** y mandarle `/newbot`. Seguir las
   instrucciones (nombre + username del bot — usar nombres distintos para
   cada pipeline, ej. "Mis papers" y "Mis oportunidades"). Da un **token**,
   formato `123456789:ABC-...`.
2. Buscar tu bot nuevo por el username que le pusiste y mandarle cualquier
   mensaje (ej. "hola") — un bot no puede escribirle primero a un chat que
   nunca le escribió.
3. Abrir en el navegador `https://api.telegram.org/bot<TOKEN>/getUpdates`
   (con tu token) y copiar tu **chat_id** de `result[0].message.chat.id`.

```bash
# Prueba de humo: manda un mensaje de texto suelto (sirve para cualquiera
# de los dos bots, solo cambia que token/chat_id le pases)
TELEGRAM_BOT_TOKEN=123456789:ABC-... TELEGRAM_CHAT_ID=... \
    python scripts/send_test_telegram.py
```

### Variables de entorno

| Variable | Pipeline | Obligatoria | Descripción |
|---|---|---|---|
| `TELEGRAM_BOT_TOKEN` | oportunidades | sí | Token del bot de oportunidades, dado por @BotFather. |
| `TELEGRAM_CHAT_ID` | oportunidades | sí | chat_id destino del bot de oportunidades. |
| `TELEGRAM_BOT_TOKEN_PAPERS` | papers | sí | Token del bot de papers (otro `/newbot`, separado del de arriba). |
| `TELEGRAM_CHAT_ID_PAPERS` | papers | sí | chat_id destino del bot de papers. |

**Límite:** Telegram permite hasta 4096 caracteres por mensaje de texto (y
1024 de caption en un documento); `send_telegram_message` /
`send_telegram_document` levantan `TelegramError` si se supera (las fichas
de oportunidades caben cómodamente; las de papers, ver nota de longitud en
la sección de arriba, hay que vigilarlas). `send_papers.py` manda la ficha
como mensaje de texto y el PDF por separado con `send_telegram_document`
(sin caption, para no toparse con ese límite más chico).

---

## Automatización (Parte F)

Los dos pipelines corren solos, sin intervención manual, vía GitHub Actions
— cada uno con su propio workflow, horario y secrets, para no pisarse:

| Workflow | Script | Horario (hora Colombia) |
|---|---|---|
| `.github/workflows/opportunities.yml` | `scripts/send_opportunities.py` | Lunes, miércoles y viernes 1:00pm |
| `.github/workflows/papers.yml` | `scripts/send_papers.py` | Lunes, martes y jueves 7:00am |

**Setup (una sola vez por workflow), en la página del repo en GitHub:**
1. Completar el setup de Telegram de la sección anterior (un bot por
   pipeline — dos bots en total).
2. Settings → Secrets and variables → Actions → New repository secret, y
   agregar:
   - Para oportunidades: `ANTHROPIC_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.
   - Para papers: `ANTHROPIC_API_KEY` (se puede reusar el mismo secret),
     `OPENALEX_MAILTO`, `TELEGRAM_BOT_TOKEN_PAPERS`, `TELEGRAM_CHAT_ID_PAPERS`.
3. Mergear la rama con estos workflows a la rama default del repo (`main`) —
   los triggers de horario (`schedule`) de GitHub Actions **solo** se activan
   con la versión del workflow que está en la rama default, no en una rama
   feature. Sin este paso el cron queda inactivo aunque el archivo ya exista.

**Para probarlo sin esperar al cron:** pestaña Actions del repo → elegir
"Oportunidades académicas por Telegram" o "Papers académicos por Telegram"
→ Run workflow (dispara el `workflow_dispatch`, que sí funciona desde
cualquier rama que tenga el archivo).

**Cómo persiste el estado entre corridas:** cada corrida del workflow parte
de un checkout limpio (no hay disco persistente en GitHub Actions), así que
`data/opportunities_seen.json` y `data/papers_sent.json` se guardan/restauran
con `actions/cache` en vez de comprometerlos al repo — evita tanto perder el
historial de lo ya enviado como llenar el repo de commits automáticos.

**Costo a tener en cuenta:** cada corrida hace llamados reales a la API de
Claude (oportunidades con `web_search`/`web_fetch`; papers con `messages.create`
sobre PDFs completos, más caro por corrida pero solo corre 3 veces/semana);
Telegram en sí es gratis.
