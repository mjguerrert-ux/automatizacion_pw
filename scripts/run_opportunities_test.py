"""
Corrida de punta a punta del pipeline de oportunidades (Partes A + B + ficha):
descubre candidatos, verifica cada uno visitando su pagina, y muestra el
mensaje de WhatsApp ya armado para las oportunidades relevantes. Marca como
"vistas" las que se muestran, para no repetirlas en la siguiente corrida.

No manda nada por WhatsApp todavia (Parte E, pendiente, compartida con el
pipeline de papers).

Uso:
    ANTHROPIC_API_KEY=sk-ant-... python scripts/run_opportunities_test.py
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from opportunities.discovery import DiscoveryError, discover_opportunities  # noqa: E402
from opportunities.extract import ExtractError, extract_fichas  # noqa: E402
from opportunities.format import format_whatsapp_message  # noqa: E402
from opportunities.store import load_seen, mark_seen  # noqa: E402


def main() -> None:
    print("Paso 1/2: descubriendo candidatos...\n")
    try:
        discovery = discover_opportunities()
    except DiscoveryError as e:
        sys.exit(f"Error en el descubrimiento: {e}")

    seen = load_seen()
    candidates = [c for c in discovery.candidates if c.source_url not in seen]
    skipped = len(discovery.candidates) - len(candidates)
    print(f"{len(discovery.candidates)} candidatos encontrados ({skipped} ya vistos, se omiten).")

    if not candidates:
        sys.exit("Nada nuevo para verificar en esta corrida.")

    print(f"\nPaso 2/2: verificando {len(candidates)} candidatos y armando la ficha...\n")
    try:
        result = extract_fichas(candidates)
    except ExtractError as e:
        sys.exit(f"Error en la verificacion: {e}")

    new_links = []
    n_relevant = 0
    for ev in result.evaluations:
        c = candidates[ev.candidate_index]
        print(f"--- Candidato {ev.candidate_index}: {c.title_raw} ---")
        print(f"Relevante: {ev.is_relevant} — {ev.reasoning}\n")

        if ev.is_relevant and ev.ficha:
            n_relevant += 1
            new_links.append(ev.ficha.apply_link or c.source_url)
            print(format_whatsapp_message(ev.ficha))
            print()

    mark_seen(new_links + [c.source_url for c in candidates])

    print(f"=== {n_relevant} oportunidad(es) relevante(s) de {len(candidates)} candidatos ===")


if __name__ == "__main__":
    main()
