"""
Arma el mensaje de WhatsApp con la ficha fija a partir de una OpportunityFicha
ya verificada (Parte B, `opportunities.extract`). No decide relevancia ni
manda el mensaje: eso es extract.py y whatsapp.client (Parte E).

Expone dos formas de la misma ficha:
- format_whatsapp_message: texto plano completo, para mostrar en pantalla o
  mandar como mensaje libre (send_whatsapp_message - solo sirve dentro de
  una sesion, ej. contra el sandbox).
- ficha_content_variables: variables numeradas ("1".."8") para mandar con
  una plantilla aprobada por Meta (send_whatsapp_template), que es lo que
  hace falta para el envio automatico real. La plantilla en Twilio debe
  declararse con el mismo texto/orden que format_whatsapp_message, una
  variable por campo (ver README > Automatización).
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


def ficha_content_variables(ficha: OpportunityFicha) -> dict[str, str]:
    requirements = "; ".join(ficha.requirements) or "no especificados"

    return {
        "1": ficha.position,
        "2": ficha.institution,
        "3": ficha.thematic_focus,
        "4": ficha.countries,
        "5": ficha.funding,
        "6": ficha.deadline or "no especificada",
        "7": requirements,
        "8": ficha.apply_link,
    }
