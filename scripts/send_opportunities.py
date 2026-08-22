"""
Corrida real del pipeline de oportunidades: descubre candidatos, verifica
cada uno, arma la ficha y MANDA por Telegram cada oportunidad relevante que
todavia no se hubiera notificado. A diferencia de run_opportunities_test.py
(que solo imprime en pantalla), esta si envia mensajes reales.

Solo marca una oportunidad como "vista" (para no repetirla en la siguiente
corrida) despues de que el envio por Telegram fue exitoso - si falla, la
oportunidad se vuelve a intentar en la proxima corrida.

Uso:
    ANTHROPIC_API_KEY=sk-ant-... \\
        TELEGRAM_BOT_TOKEN=123456789:ABC-... TELEGRAM_CHAT_ID=... \\
        python scripts/send_opportunities.py
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from opportunities.discovery import DEFAULT_MODEL as DEFAULT_DISCOVERY_MODEL  # noqa: E402
from opportunities.discovery import DiscoveryError, discover_opportunities  # noqa: E402
from opportunities.extract import DEFAULT_MODEL as DEFAULT_EXTRACT_MODEL  # noqa: E402
from opportunities.extract import ExtractError, extract_fichas  # noqa: E402
from opportunities.format import format_message  # noqa: E402
from opportunities.store import load_seen, mark_seen  # noqa: E402
from opportunities.usage import TokenUsage, estimate_cost_usd  # noqa: E402
from telegram.client import TelegramError, send_telegram_message  # noqa: E402


def _print_usage(label: str, model: str, usage: TokenUsage) -> None:
    cost = estimate_cost_usd(model, usage)
    cost_str = f"(~${cost:.3f} USD)" if cost is not None else "(no se pudo estimar el costo)"
    print(
        f"{label}: {usage.input_tokens:,} tokens entrada + {usage.output_tokens:,} salida, "
        f"{usage.calls} llamada(s) a {model} {cost_str}"
    )


def main() -> None:
    print("Paso 1/3: descubriendo candidatos...\n")
    try:
        discovery = discover_opportunities()
    except DiscoveryError as e:
        _print_usage("Uso de tokens (descubrimiento, antes de fallar)", DEFAULT_DISCOVERY_MODEL, e.usage)
        sys.exit(f"Error en el descubrimiento: {e}")

    _print_usage("Uso de tokens (descubrimiento)", discovery.model, discovery.usage)

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
        _print_usage("Uso de tokens (verificacion, antes de fallar)", DEFAULT_EXTRACT_MODEL, e.usage)
        sys.exit(f"Error en la verificacion: {e}")

    _print_usage("Uso de tokens (verificacion)", result.model, result.usage)

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

    print(f"\nPaso 3/3: mandando {len(relevant)} oportunidad(es) por Telegram...\n")
    n_sent = 0
    for ev in relevant:
        c = candidates[ev.candidate_index]
        try:
            message_id = send_telegram_message(format_message(ev.ficha))
        except TelegramError as e:
            print(f"[FALLO] {c.title_raw}: {e}")
            continue

        mark_seen([ev.ficha.apply_link or c.source_url])
        n_sent += 1
        print(f"[OK] {c.title_raw} (message_id {message_id})")

    print(f"\n=== {n_sent}/{len(relevant)} oportunidades enviadas ===")

    total_cost_discovery = estimate_cost_usd(discovery.model, discovery.usage)
    total_cost_extract = estimate_cost_usd(result.model, result.usage)
    if total_cost_discovery is not None and total_cost_extract is not None:
        print(f"Costo total estimado de esta corrida: ~${total_cost_discovery + total_cost_extract:.3f} USD")


if __name__ == "__main__":
    main()
