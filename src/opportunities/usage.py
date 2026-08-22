"""
Estimacion de costo en USD a partir del uso de tokens que devuelve la API de
Claude, para que send_opportunities.py pueda imprimir cuanto costo cada
corrida real (en vez de que haya que adivinarlo o mirar la consola de
Anthropic despues).

La tabla de precios esta hardcodeada y es una ESTIMACION, no una factura -
Anthropic puede cambiar precios (algunos son de lanzamiento, con vencimiento)
y esto no lo sabe. Actualizar _PRICING_PER_MTOK si cambian.
"""

from __future__ import annotations

from dataclasses import dataclass

# USD por millon de tokens (input, output).
_PRICING_PER_MTOK: dict[str, tuple[float, float]] = {
    "claude-opus-5": (5.00, 25.00),
    "claude-sonnet-5": (2.00, 10.00),  # precio de lanzamiento hasta 2026-08-31
    "claude-haiku-4-5": (1.00, 5.00),
}


@dataclass
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    calls: int = 0

    def __add__(self, other: TokenUsage) -> TokenUsage:
        return TokenUsage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            calls=self.calls + other.calls,
        )


def usage_from_response(response) -> TokenUsage:
    usage = getattr(response, "usage", None)
    return TokenUsage(
        input_tokens=getattr(usage, "input_tokens", 0) or 0,
        output_tokens=getattr(usage, "output_tokens", 0) or 0,
        calls=1,
    )


def estimate_cost_usd(model: str, usage: TokenUsage) -> float | None:
    """None si `model` no esta en la tabla de precios (no se puede estimar)."""
    pricing = _PRICING_PER_MTOK.get(model)
    if pricing is None:
        return None
    input_price, output_price = pricing
    return (
        usage.input_tokens / 1_000_000 * input_price
        + usage.output_tokens / 1_000_000 * output_price
    )
