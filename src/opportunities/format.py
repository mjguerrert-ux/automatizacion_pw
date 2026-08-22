"""
Arma el mensaje con la ficha fija a partir de una OpportunityFicha ya
verificada (Parte B, `opportunities.extract`). No decide relevancia ni
manda el mensaje: eso es extract.py y telegram.client (Parte E).
"""

from __future__ import annotations

from opportunities.extract import OpportunityFicha


def format_message(ficha: OpportunityFicha) -> str:
    requirements = "\n".join(f"   • {r}" for r in ficha.requirements) or "   (no especificados)"

    return (
        f"🎓 Posición: {ficha.position}\n"
        f"🏛️ Institución: {ficha.institution}\n"
        f"📍 Foco temático: {ficha.thematic_focus}\n"
        f"🌍 Países involucrados: {ficha.countries}\n"
        f"💰 Salario/financiamiento: {ficha.funding}\n"
        f"📅 Fecha límite: {ficha.deadline or 'no especificada'}\n"
        f"✅ Requisitos clave:\n{requirements}\n"
        f"🔗 Link para aplicar: {ficha.apply_link}"
    )
