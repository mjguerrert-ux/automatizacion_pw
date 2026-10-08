"""
Corrida real del pipeline de oportunidades: descubre candidatos, verifica
cada uno, arma la ficha y la deja en una COLA. Manda por Telegram como mucho
1 oportunidad por corrida (la mas antigua en espera) - mandar las 6-7 que a
veces salen relevantes de una sola corrida es demasiado para revisar de
golpe (paso el 7/oct). Las demas quedan en cola para las siguientes corridas.

Un fallo en el descubrimiento o la verificacion no impide intentar mandar lo
que ya hubiera en cola de corridas anteriores - cada etapa se degrada sola.

Solo se saca una oportunidad de la cola (y se marca "vista") despues de que
el envio por Telegram fue exitoso - si falla, se reintenta en la proxima
corrida.

Uso:
    ANTHROPIC_API_KEY=sk-ant-... \\
        TELEGRAM_BOT_TOKEN=123456789:ABC-... TELEGRAM_CHAT_ID=... \\
        python scripts/send_opportunities.py
"""

import os
import sys
from dataclasses import asdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from opportunities.discovery import DEFAULT_MODEL as DEFAULT_DISCOVERY_MODEL  # noqa: E402
from opportunities.discovery import DiscoveryError, discover_opportunities  # noqa: E402
from opportunities.extract import DEFAULT_MODEL as DEFAULT_EXTRACT_MODEL  # noqa: E402
from opportunities.extract import ExtractError, OpportunityFicha, extract_fichas  # noqa: E402
from opportunities.format import format_message  # noqa: E402
from opportunities.store import load_queue, load_seen, mark_seen, save_queue  # noqa: E402
from opportunities.usage import TokenUsage, estimate_cost_usd  # noqa: E402
from telegram.client import TelegramError, send_telegram_message  # noqa: E402

_FICHA_FIELDS = (
    "position",
    "institution",
    "thematic_focus",
    "countries",
    "funding",
    "deadline",
    "requirements",
    "apply_link",
)


def _print_usage(label: str, model: str, usage: TokenUsage) -> None:
    cost = estimate_cost_usd(model, usage)
    cost_str = f"(~${cost:.3f} USD)" if cost is not None else "(no se pudo estimar el costo)"
    print(
        f"{label}: {usage.input_tokens:,} tokens entrada + {usage.output_tokens:,} salida, "
        f"{usage.calls} llamada(s) a {model} {cost_str}"
    )


def _discover_and_queue(seen: set[str], queue: list[dict]) -> None:
    """Descubre + verifica candidatos nuevos y los agrega a `queue` (en \
    sitio). Si descubrimiento o verificacion fallan, imprime el error y el \
    costo gastado hasta ahi, y deja la cola como estaba - no es fatal."""
    print("Paso 1/3: descubriendo candidatos...\n")
    try:
        discovery = discover_opportunities()
    except DiscoveryError as e:
        _print_usage("Uso de tokens (descubrimiento, antes de fallar)", DEFAULT_DISCOVERY_MODEL, e.usage)
        print(f"Error en el descubrimiento (se continua con la cola existente, si hay): {e}")
        return

    _print_usage("Uso de tokens (descubrimiento)", discovery.model, discovery.usage)

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
        print(f"Error en la verificacion (se continua con la cola existente, si hay): {e}")
        return

    _print_usage("Uso de tokens (verificacion)", result.model, result.usage)

    relevant = [ev for ev in result.evaluations if ev.is_relevant and ev.ficha]
    # Los no relevantes (incluye vencidas - ver extract.py) se marcan como
    # vistos, para no re-verificarlas.
    not_relevant_urls = [
        candidates[ev.candidate_index].source_url
        for ev in result.evaluations
        if not (ev.is_relevant and ev.ficha)
    ]
    mark_seen(not_relevant_urls)

    queued_links = {item["apply_link"] for item in queue}
    newly_queued_urls = []
    n_added = 0
    for ev in relevant:
        c = candidates[ev.candidate_index]
        link = ev.ficha.apply_link or c.source_url
        if link in queued_links:
            continue
        queue.append({**asdict(ev.ficha), "title_raw": c.title_raw})
        queued_links.add(link)
        newly_queued_urls.append(link)
        n_added += 1

    # Se marcan vistas apenas entran a la cola (no cuando se manden): asi
    # discovery no las vuelve a encontrar y gastar verificacion de nuevo
    # mientras esperan su turno.
    mark_seen(newly_queued_urls)

    if n_added:
        print(f"{n_added} oportunidad(es) nueva(s) agregada(s) a la cola (quedan {len(queue)} en espera).")
    else:
        print("Ningun candidato nuevo resulto relevante en esta corrida.")


def main() -> None:
    seen = load_seen()
    queue = load_queue()

    _discover_and_queue(seen, queue)
    save_queue(queue)

    if not queue:
        print("\nNo hay ninguna oportunidad en cola para mandar hoy.")
        return

    print(f"\nPaso 3/3: mandando 1 oportunidad por Telegram (quedan {len(queue) - 1} en cola despues)...\n")
    next_item = queue[0]
    ficha = OpportunityFicha(**{k: next_item[k] for k in _FICHA_FIELDS})
    try:
        message_id = send_telegram_message(format_message(ficha))
    except TelegramError as e:
        print(f"[FALLO] {next_item['title_raw']}: {e} - se reintenta en la proxima corrida.")
        return

    queue.pop(0)
    save_queue(queue)
    print(f"[OK] {next_item['title_raw']} (message_id {message_id})")


if __name__ == "__main__":
    main()
