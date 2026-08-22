"""
Parte A del pipeline de oportunidades: probar el descubrimiento de candidatos
con la herramienta de busqueda web.

Uso:
    ANTHROPIC_API_KEY=sk-ant-... python scripts/discover_test_opportunities.py
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from opportunities.discovery import DiscoveryError, discover_opportunities  # noqa: E402


def main() -> None:
    print("Buscando fellowships pre-doctorales / posiciones RA en educacion...\n")

    try:
        result = discover_opportunities()
    except DiscoveryError as e:
        sys.exit(f"Error en el descubrimiento: {e}")

    if not result.candidates:
        sys.exit("No se encontraron candidatos en esta corrida.")

    for i, c in enumerate(result.candidates):
        print(f"--- Candidato {i} ---")
        print(f"Titulo:      {c.title_raw}")
        print(f"Institucion: {c.institution_raw}")
        print(f"URL:         {c.source_url}")
        print(f"Notas:       {c.notes}")
        print()

    print(f"Total: {len(result.candidates)} candidatos (sin verificar todavia).")


if __name__ == "__main__":
    main()
