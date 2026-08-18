"""Motor de costeo de importación: replica el papel de trabajo "PAPEL COSTOS"
(hoja COSTOS) y lo generaliza.

Por cada partida del pedimento:

    costo_unitario (landed)  = precio_unitario + dta_pza + igi_pza + gastos_pza
    precio_unitario_venta    = costo_unitario + utilidad_pza
    subtotal                 = cantidad × precio_unitario_venta
    iva_16                   = subtotal × 16%
    total                    = subtotal + iva_16
    dif_iva                  = iva_16 − iva_importacion   (col AJ del Excel)

Donde:
    igi_pza  = igi_partida / cantidad             (col U: el IGI ya viene por partida)
    dta_pza  = prorrateo(dta) / cantidad           (cols R,S)
    gastos_pza = prorrateo(gastos_adicionales) / cantidad   (cols W,X: fletes, seguros, maniobras...)
    utilidad_pza = prorrateo(utilidad) / cantidad  (cols Y,Z,AA)

"prorrateo" reparte un monto a nivel pedimento entre las partidas según el
método elegido. El Excel usa PARTES IGUALES (monto / número de partidas); se
ofrecen además por valor aduana, por cantidad y por peso.

Todo en Decimal. Los importes monetarios finales se cuantizan a 2 decimales y
los unitarios a 6, para no arrastrar redondeos por partida × miles de piezas.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Iterable, Protocol

METODOS_PRORRATEO = ("partes_iguales", "valor_aduana", "cantidad", "peso")
TASA_IVA = Decimal("0.16")

_Q2 = Decimal("0.01")
_Q6 = Decimal("0.000001")


def q2(v: Decimal) -> Decimal:
    return v.quantize(_Q2, rounding=ROUND_HALF_UP)


def q6(v: Decimal) -> Decimal:
    return v.quantize(_Q6, rounding=ROUND_HALF_UP)


class PartidaLike(Protocol):
    """Lo mínimo que el motor necesita de una partida (modelo ORM o dataclass del parser)."""

    secuencia: int
    precio_unitario: Decimal
    valor_aduana: Decimal
    cantidad_umc: Decimal
    cantidad_umt: Decimal | None
    igi: Decimal
    iva: Decimal


@dataclass(frozen=True)
class CosteoPartida:
    secuencia: int
    cantidad: Decimal
    precio_unitario: Decimal
    dta_asignado: Decimal
    dta_pza: Decimal
    igi_pza: Decimal
    gastos_asignados: Decimal
    gastos_pza: Decimal
    utilidad_asignada: Decimal
    utilidad_pza: Decimal
    costo_unitario: Decimal  # landed cost, sin utilidad → va al inventario
    precio_unitario_venta: Decimal  # con utilidad → refactura al cliente
    subtotal: Decimal
    iva_16: Decimal
    total: Decimal
    dif_iva: Decimal


@dataclass(frozen=True)
class CosteoPedimento:
    partidas: list[CosteoPartida]
    dta: Decimal
    gastos_adicionales: Decimal
    utilidad: Decimal
    igi_total: Decimal
    iva_importacion_total: Decimal
    costo_total: Decimal  # Σ cantidad × costo_unitario
    subtotal_venta: Decimal
    iva_venta: Decimal
    total_venta: Decimal
    dif_iva_total: Decimal


def _pesos(partidas: list[PartidaLike], metodo: str) -> list[Decimal]:
    """Base de reparto por partida según el método. Si la base es 0 (p. ej. sin
    peso declarado), cae a partes iguales para no dividir entre cero."""
    n = len(partidas)
    if metodo == "valor_aduana":
        base = [Decimal(p.valor_aduana) for p in partidas]
    elif metodo == "cantidad":
        base = [Decimal(p.cantidad_umc) for p in partidas]
    elif metodo == "peso":
        base = [Decimal(p.cantidad_umt or 0) for p in partidas]
    else:  # partes_iguales
        base = [Decimal(1)] * n
    total = sum(base, Decimal("0"))
    if total <= 0:
        return [Decimal(1) / n] * n
    return [b / total for b in base]


def prorratear(monto: Decimal, partidas: list[PartidaLike], metodo: str) -> list[Decimal]:
    """Reparte `monto` entre las partidas. La última absorbe el residuo de redondeo
    para que la suma cuadre al centavo con el monto original."""
    if not partidas:
        return []
    monto = Decimal(monto)
    pesos = _pesos(partidas, metodo)
    asignados = [q2(monto * w) for w in pesos[:-1]]
    asignados.append(q2(monto - sum(asignados, Decimal("0"))))
    return asignados


def costear(
    partidas: Iterable[PartidaLike],
    *,
    dta: Decimal,
    gastos_adicionales: Decimal = Decimal("0"),
    utilidad: Decimal = Decimal("0"),
    metodo_prorrateo: str = "partes_iguales",
    tasa_iva: Decimal = TASA_IVA,
) -> CosteoPedimento:
    if metodo_prorrateo not in METODOS_PRORRATEO:
        raise ValueError(f"Método de prorrateo desconocido: {metodo_prorrateo}")

    lista = list(partidas)
    dta_x = prorratear(Decimal(dta or 0), lista, metodo_prorrateo)
    gastos_x = prorratear(Decimal(gastos_adicionales or 0), lista, metodo_prorrateo)
    util_x = prorratear(Decimal(utilidad or 0), lista, metodo_prorrateo)

    resultados: list[CosteoPartida] = []
    for p, dta_a, gas_a, uti_a in zip(lista, dta_x, gastos_x, util_x):
        cant = Decimal(p.cantidad_umc)
        if cant <= 0:
            raise ValueError(f"La partida {p.secuencia} tiene cantidad 0; no se puede costear por pieza")
        precio = Decimal(p.precio_unitario)
        dta_pza = q6(dta_a / cant)
        igi_pza = q6(Decimal(p.igi) / cant)
        gastos_pza = q6(gas_a / cant)
        util_pza = q6(uti_a / cant)
        costo_unit = q6(precio + dta_pza + igi_pza + gastos_pza)
        precio_venta = q6(costo_unit + util_pza)
        subtotal = q2(cant * precio_venta)
        iva_16 = q2(subtotal * tasa_iva)
        resultados.append(
            CosteoPartida(
                secuencia=p.secuencia,
                cantidad=cant,
                precio_unitario=precio,
                dta_asignado=dta_a,
                dta_pza=dta_pza,
                igi_pza=igi_pza,
                gastos_asignados=gas_a,
                gastos_pza=gastos_pza,
                utilidad_asignada=uti_a,
                utilidad_pza=util_pza,
                costo_unitario=costo_unit,
                precio_unitario_venta=precio_venta,
                subtotal=subtotal,
                iva_16=iva_16,
                total=q2(subtotal + iva_16),
                dif_iva=q2(iva_16 - Decimal(p.iva)),
            )
        )

    suma = lambda attr: sum((getattr(r, attr) for r in resultados), Decimal("0"))  # noqa: E731
    return CosteoPedimento(
        partidas=resultados,
        dta=q2(Decimal(dta or 0)),
        gastos_adicionales=q2(Decimal(gastos_adicionales or 0)),
        utilidad=q2(Decimal(utilidad or 0)),
        igi_total=q2(sum((Decimal(p.igi) for p in lista), Decimal("0"))),
        iva_importacion_total=q2(sum((Decimal(p.iva) for p in lista), Decimal("0"))),
        costo_total=q2(sum((r.cantidad * r.costo_unitario for r in resultados), Decimal("0"))),
        subtotal_venta=suma("subtotal"),
        iva_venta=suma("iva_16"),
        total_venta=suma("total"),
        dif_iva_total=suma("dif_iva"),
    )
