"""
Arma el mensaje de WhatsApp con la ficha fija a partir de una OpportunityFicha
ya verificada (Parte B, `opportunities.extract`). No decide relevancia ni
manda el mensaje: eso es extract.py y la Parte E (envio, todavia no
implementada, compartida con el pipeline de papers).
"""

from __future__ import annotations

from opportunities.extract import OpportunityFicha


def format_whatsapp_message(ficha: OpportunityFicha) -> str:
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
