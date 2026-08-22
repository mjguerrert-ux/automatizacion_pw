"""
Corrida real del pipeline de oportunidades: descubre candidatos, verifica
cada uno, arma la ficha y MANDA por WhatsApp cada oportunidad relevante que
todavia no se hubiera notificado. A diferencia de run_opportunities_test.py
(que solo imprime en pantalla), esta si envia mensajes reales.

Solo marca una oportunidad como "vista" (para no repetirla en la siguiente
corrida) despues de que el envio por WhatsApp fue exitoso - si Twilio falla,
la oportunidad se vuelve a intentar en la proxima corrida.

Uso:
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
from opportunities.format import format_whatsapp_message  # noqa: E402
from opportunities.store import load_seen, mark_seen  # noqa: E402
from whatsapp.client import WhatsAppError, send_whatsapp_message  # noqa: E402


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

    print(f"\nPaso 3/3: mandando {len(relevant)} oportunidad(es) por WhatsApp...\n")
    n_sent = 0
    for ev in relevant:
        c = candidates[ev.candidate_index]
        message = format_whatsapp_message(ev.ficha)
        try:
            sid = send_whatsapp_message(message)
        except WhatsAppError as e:
            print(f"[FALLO] {c.title_raw}: {e}")
            continue

        mark_seen([ev.ficha.apply_link or c.source_url])
        n_sent += 1
        print(f"[OK] {c.title_raw} (SID {sid})")

    print(f"\n=== {n_sent}/{len(relevant)} oportunidades enviadas ===")


if __name__ == "__main__":
    main()
