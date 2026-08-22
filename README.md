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
- **E.** Envío por WhatsApp — ✅ implementado (`src/whatsapp/`, compartido con
  el pipeline de oportunidades), pendiente conectarlo aquí una vez existan C y D.
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
src/whatsapp/
  client.py     # Parte E: envío por WhatsApp vía Twilio (compartido con papers)
scripts/
  discover_test_opportunities.py  # Parte A: prueba solo el descubrimiento
  run_opportunities_test.py       # Corrida de prueba: descubre + verifica + imprime la ficha (no envía)
  send_opportunities.py           # Corrida real: descubre + verifica + ENVÍA por WhatsApp
  send_test_whatsapp.py           # Prueba de humo de Twilio, compartida con el pipeline de papers
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

# Corrida real: descubre, verifica y ENVÍA por WhatsApp cada oportunidad nueva
ANTHROPIC_API_KEY=sk-ant-... \
    TWILIO_ACCOUNT_SID=AC... TWILIO_AUTH_TOKEN=... \
    TWILIO_WHATSAPP_TO=whatsapp:+573001234567 \
    python scripts/send_opportunities.py
```

Cada corrida guarda en `data/opportunities_seen.json` (no versionado) los
links ya notificados/enviados, para no repetir la misma oportunidad en la
siguiente corrida mientras siga abierta. `send_opportunities.py` solo marca
una oportunidad como vista después de que el envío por WhatsApp fue exitoso;
si Twilio falla, se reintenta en la próxima corrida.

### Limitaciones conocidas

- La cobertura depende de qué tan bien indexadas estén las páginas de los
  labs/profesores/organismos en los motores de búsqueda que usa `web_search`;
  no hay garantía de encontrar el 100% de las convocatorias abiertas.

---

## Envío por WhatsApp (Parte E)

Módulo compartido por ambos pipelines (`src/whatsapp/client.py`), vía la API
de WhatsApp de [Twilio](https://www.twilio.com/docs/whatsapp/quickstart/python).
Twilio (y WhatsApp/Meta detrás) distinguen dos formas de mandar un mensaje,
y cuál te sirve depende de si el envío es automático o no:

- **Texto libre** (`send_whatsapp_message`, con `body`): solo se entrega
  como *respuesta* dentro de una sesión de 24h que abre el destinatario al
  escribirte. Sirve para el **sandbox de pruebas** de Twilio.
- **Plantilla aprobada por Meta** (`send_whatsapp_template`, con
  `content_sid`): obligatoria para cualquier mensaje que **vos** iniciás sin
  que la usuaria haya escrito antes — exactamente lo que hace el cron
  (Parte F) cada corrida. El sandbox **no soporta** plantillas propias, así
  que el cron automático necesita un WhatsApp sender de producción.

En resumen: el sandbox alcanza para probar el pipeline manualmente, pero
para el envío automático real hace falta completar el registro del sender
y crear una plantilla — son los pasos 2 y 3 de abajo.

### 1. Sandbox (pruebas manuales rápidas)

1. Crear una cuenta de Twilio (gratis).
2. En la consola: Messaging → Try it out → Send a WhatsApp message (o
   directamente [console.twilio.com/console/sms/whatsapp/sandbox](https://www.twilio.com/console/sms/whatsapp/sandbox)
   — el sandbox vive en la consola "legacy", no en la pantalla nueva de
   "Numbers & Senders").
3. Unir tu número al sandbox mandándole por WhatsApp el código ("join
   ...") que te da esa página.
4. Copiar `Account SID` y `Auth Token` de Account Info.

```bash
# Prueba de humo: manda un mensaje de texto suelto (funciona ~24h desde que
# te uniste, o desde tu ultimo mensaje al sandbox)
TWILIO_ACCOUNT_SID=AC... TWILIO_AUTH_TOKEN=... \
    TWILIO_WHATSAPP_TO=whatsapp:+573001234567 \
    python scripts/send_test_whatsapp.py
```

Con esto ya podés correr `run_opportunities_test.py` (imprime, no manda) y
`send_opportunities.py` sin `TWILIO_CONTENT_SID` (manda texto libre) para
validar la calidad del pipeline. **No sirve para el cron** — ver la nota de
`send_opportunities.py` cuando corre sin plantilla.

### 2. Sender de producción (necesario para el cron)

En la consola nueva: **Numbers & Senders → WhatsApp → Create new sender**.
El flujo pide, en orden:
1. Elegir un número (podés usar uno de Twilio, no hace falta uno propio).
2. Conectar con Meta ("Continue with Facebook") e iniciar sesión.
3. Crear o elegir un **Meta Business Portfolio** (se puede crear ahí mismo
   si no tenés uno).
4. Crear o elegir una **WhatsApp Business Account (WABA)**.
5. Completar el perfil: nombre de cuenta, nombre visible para el
   destinatario, categoría del "negocio", y opcionalmente descripción/sitio.
6. Verificar el número (SMS o llamada).

El sender queda activo apenas termina el flujo, con límites iniciales (~250
mensajes/24h) hasta que Meta complete la verificación empresarial completa
— de sobra para 3 corridas/semana con un solo destinatario.

### 3. Content Template (para que el cron pueda mandar)

En la consola: **Content Template Builder** (link en la misma pantalla de
WhatsApp Senders). Creá una plantilla con este texto exacto, para que
coincida con `format_whatsapp_message` / `ficha_content_variables`
(`src/opportunities/format.py`):

```
🎓 Posición: {{1}}
🏛️ Institución: {{2}}
📍 Foco temático: {{3}}
🌍 Países involucrados: {{4}}
💰 Salario/financiamiento: {{5}}
📅 Fecha límite: {{6}}
✅ Requisitos clave: {{7}}
🔗 Link para aplicar: {{8}}
```

Categoría: "Utility" (es una notificación informativa, no marketing).
Mandala a aprobación — Meta suele resolver en minutos a pocas horas para
plantillas simples como esta. Una vez aprobada, la consola te da un
`content_sid` (empieza con `HX...`); esa es tu variable `TWILIO_CONTENT_SID`.

### Variables de entorno

| Variable | Obligatoria | Descripción |
|---|---|---|
| `TWILIO_ACCOUNT_SID` | sí | Desde la consola de Twilio. |
| `TWILIO_AUTH_TOKEN` | sí | Desde la consola de Twilio. |
| `TWILIO_WHATSAPP_TO` | sí | Número destino, formato `whatsapp:+<código país><número>`. |
| `TWILIO_CONTENT_SID` | para el cron | ID de la plantilla aprobada (paso 3). Sin ella, `send_opportunities.py` cae a texto libre (solo sirve con sesión abierta). |
| `TWILIO_WHATSAPP_FROM` | no | Por defecto usa el número de sandbox. Poné acá tu número de sender de producción (paso 2) una vez lo tengas. |

**Límite:** Twilio permite hasta 1600 caracteres por mensaje de texto libre;
`send_whatsapp_message` levanta `WhatsAppError` si lo supera (no aplica a
`send_whatsapp_template`, que usa el límite de la plantilla).

---

## Automatización (Parte F)

El pipeline de oportunidades corre solo, sin intervención manual, vía
GitHub Actions: `.github/workflows/opportunities.yml` ejecuta
`scripts/send_opportunities.py` **lunes, miércoles y viernes a las 8:00am
hora Colombia**.

**Setup (una sola vez), en la página del repo en GitHub:**
1. Completar los pasos 2 y 3 de la sección "Envío por WhatsApp" arriba
   (sender de producción + plantilla aprobada) — sin `TWILIO_CONTENT_SID`
   el workflow manda texto libre, que el cron no puede entregar (no hay
   sesión abierta, nadie le escribió antes).
2. Settings → Secrets and variables → Actions → New repository secret, y
   agregar: `ANTHROPIC_API_KEY`, `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`,
   `TWILIO_WHATSAPP_TO`, `TWILIO_CONTENT_SID` (y `TWILIO_WHATSAPP_FROM` con
   tu número de sender de producción).
3. Mergear la rama con este workflow a la rama default del repo (`main`) —
   los triggers de horario (`schedule`) de GitHub Actions **solo** se activan
   con la versión del workflow que está en la rama default, no en una rama
   feature. Sin este paso el cron queda inactivo aunque el archivo ya exista.

**Para probarlo sin esperar al cron:** pestaña Actions del repo →
"Oportunidades académicas por WhatsApp" → Run workflow (dispara el
`workflow_dispatch`, que sí funciona desde cualquier rama que tenga el
archivo).

**Cómo persiste el estado entre corridas:** cada corrida del workflow parte
de un checkout limpio (no hay disco persistente en GitHub Actions), así que
`data/opportunities_seen.json` se guarda/restaura con `actions/cache` en vez
de comprometerlo al repo — evita tanto perder el historial de oportunidades
ya enviadas como llenar el repo de commits automáticos.

**Costo a tener en cuenta:** cada corrida hace llamados reales a la API de
Claude (con `web_search`/`web_fetch`) y, si hay oportunidades nuevas, a
Twilio — no es gratis, aunque para 3 corridas/semana el volumen es bajo.

### Pendiente

- El pipeline de papers (Partes C y D) no está conectado a ningún workflow
  todavía — una vez existan, puede agregarse un job análogo a este mismo
  archivo o uno separado (`papers.yml`) que use el mismo `src/whatsapp/`.
