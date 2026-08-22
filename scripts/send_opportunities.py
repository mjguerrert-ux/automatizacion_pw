"""
Corrida real del pipeline de oportunidades: descubre candidatos, verifica
cada uno, arma la ficha y MANDA por WhatsApp cada oportunidad relevante que
todavia no se hubiera notificado. A diferencia de run_opportunities_test.py
(que solo imprime en pantalla), esta si envia mensajes reales.

Solo marca una oportunidad como "vista" (para no repetirla en la siguiente
corrida) despues de que el envio por WhatsApp fue exitoso - si Twilio falla,
la oportunidad se vuelve a intentar en la proxima corrida.

Este script SIEMPRE inicia la conversacion (nunca responde a un mensaje de
la usuaria), asi que WhatsApp exige una plantilla aprobada por Meta: si
TWILIO_CONTENT_SID esta definida, manda con esa plantilla (send_whatsapp_template,
la via correcta para el cron de la Parte F). Si no esta definida, cae a texto
libre (send_whatsapp_message), que solo entrega si hay una sesion de 24h
abierta (ej. le acabas de escribir al sandbox) - sirve para probar el
pipeline manualmente mientras registras la plantilla, no para el cron.

Uso (con plantilla, recomendado para produccion):
    ANTHROPIC_API_KEY=sk-ant-... \\
        TWILIO_ACCOUNT_SID=AC... TWILIO_AUTH_TOKEN=... \\
        TWILIO_WHATSAPP_TO=whatsapp:+573001234567 \\
        TWILIO_CONTENT_SID=HX... \\
        python scripts/send_opportunities.py

Uso (texto libre, solo pruebas manuales dentro de una sesion):
    ANTHROPIC_API_KEY=sk-ant-... \\
        TWILIO_ACCOUNT_SID=AC... TWILIO_AUTH_TOKEN=... \\
        TWILIO_WHATSAPP_TO=whatsapp:+573001234567 \\
        python scripts/send_opportunities.py
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from opportunities.discovery import DiscoveryError, discover_opportunities  # noqa: E402
from opportunities.extract import ExtractError, extract_fichas  # noqa: E402
from opportunities.format import ficha_content_variables, format_whatsapp_message  # noqa: E402
from opportunities.store import load_seen, mark_seen  # noqa: E402
from whatsapp.client import (  # noqa: E402
    WhatsAppError,
    send_whatsapp_message,
    send_whatsapp_template,
)


def main() -> None:
    print("Paso 1/3: descubriendo candidatos...\n")
    try:
        discovery = discover_opportunities()
    except DiscoveryError as e:
        sys.exit(f"Error en el descubrimiento: {e}")

    seen = load_seen()
    candidates = [c for c in discovery.candidates if c.source_url not in seen]
    skipped = len(discovery.candidates) - len(candidates)
    print(f"{len(discovery.candidates)} candidatos encontrados ({skipped} ya vistos, se omiten).")

    if not candidates:
        print("Nada nuevo para verificar en esta corrida.")
        return

    print(f"\nPaso 2/3: verificando {len(candidates)} candidatos y armando la ficha...\n")
    try:
        result = extract_fichas(candidates)
    except ExtractError as e:
        sys.exit(f"Error en la verificacion: {e}")

    relevant = [ev for ev in result.evaluations if ev.is_relevant and ev.ficha]
    # Los no relevantes tambien se marcan como vistos, para no re-verificarlos.
    not_relevant_urls = [
        candidates[ev.candidate_index].source_url
        for ev in result.evaluations
        if not (ev.is_relevant and ev.ficha)
    ]
    mark_seen(not_relevant_urls)

    if not relevant:
        print("Ningun candidato nuevo resulto relevante en esta corrida.")
        return

    content_sid = os.environ.get("TWILIO_CONTENT_SID")
    if not content_sid:
        print(
            "AVISO: TWILIO_CONTENT_SID no esta definida - mandando como texto "
            "libre, que solo entrega dentro de una sesion de 24h abierta por "
            "la usuaria. Para el cron automatico (sin sesion previa) hace "
            "falta una plantilla aprobada por Meta. Ver README > Automatización.\n"
        )

    print(f"Paso 3/3: mandando {len(relevant)} oportunidad(es) por WhatsApp...\n")
    n_sent = 0
    for ev in relevant:
        c = candidates[ev.candidate_index]
        try:
            if content_sid:
                sid = send_whatsapp_template(content_sid, ficha_content_variables(ev.ficha))
            else:
                sid = send_whatsapp_message(format_whatsapp_message(ev.ficha))
        except WhatsAppError as e:
            print(f"[FALLO] {c.title_raw}: {e}")
            continue

        mark_seen([ev.ficha.apply_link or c.source_url])
        n_sent += 1
        print(f"[OK] {c.title_raw} (SID {sid})")

    print(f"\n=== {n_sent}/{len(relevant)} oportunidades enviadas ===")


if __name__ == "__main__":
    main()
