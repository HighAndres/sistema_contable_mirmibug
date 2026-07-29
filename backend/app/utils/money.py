"""Utilidad para convertir valores monetarios a Decimal de forma consistente.

Un monto que entra por la API llega como float (JSON no tiene un tipo decimal
nativo) — to_money lo cuantiza a 2 decimales de inmediato, antes de que
participe en cualquier suma/resta, para no arrastrar el error de redondeo
binario de esos floats a través de la lógica de negocio ni a la base de datos.
"""

from decimal import ROUND_HALF_UP, Decimal


def to_money(valor: float | Decimal | str) -> Decimal:
    return Decimal(str(valor)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
