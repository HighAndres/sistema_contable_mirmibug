"""Cálculos de IVA (base flujo) e ISR provisional según el tipo de contribuyente.

Son cálculos ESTIMATIVOS a partir de los CFDI que hay en la bóveda — la "previa"
que el contador compara contra lo declarado. No sustituyen la determinación
formal (no consideran acreditamientos de periodos anteriores, retenciones,
PTU, pérdidas fiscales, deducciones personales, etc.), pero sí siguen la
mecánica legal de cada régimen para que la comparación sea útil.

Todo en Decimal; los importes finales se cuantizan a 2 decimales.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

_Q2 = Decimal("0.01")


def q2(v: Decimal | int | float) -> Decimal:
    return Decimal(str(v)).quantize(_Q2, rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------------------
# ISR — parámetros
# ---------------------------------------------------------------------------

TASA_ISR_PM = Decimal("0.30")  # art. 9 LISR

# Tarifa MENSUAL del art. 96 LISR (Anexo 8 RMF, vigente 2024-2025).
# (límite inferior, límite superior o None, cuota fija, % sobre excedente)
TARIFA_MENSUAL_ART96: list[tuple[Decimal, Decimal | None, Decimal, Decimal]] = [
    (Decimal("0.01"), Decimal("746.04"), Decimal("0.00"), Decimal("0.0192")),
    (Decimal("746.05"), Decimal("6332.05"), Decimal("14.32"), Decimal("0.0640")),
    (Decimal("6332.06"), Decimal("11128.01"), Decimal("371.83"), Decimal("0.1088")),
    (Decimal("11128.02"), Decimal("12935.82"), Decimal("893.63"), Decimal("0.1600")),
    (Decimal("12935.83"), Decimal("15487.71"), Decimal("1182.88"), Decimal("0.1792")),
    (Decimal("15487.72"), Decimal("31236.49"), Decimal("1640.18"), Decimal("0.2136")),
    (Decimal("31236.50"), Decimal("49233.00"), Decimal("5004.12"), Decimal("0.2352")),
    (Decimal("49233.01"), Decimal("93993.90"), Decimal("9236.89"), Decimal("0.3000")),
    (Decimal("93993.91"), Decimal("125325.20"), Decimal("22665.17"), Decimal("0.3200")),
    (Decimal("125325.21"), Decimal("375975.61"), Decimal("32691.18"), Decimal("0.3400")),
    (Decimal("375975.62"), None, Decimal("117912.32"), Decimal("0.3500")),
]

# RESICO personas físicas (art. 113-E LISR): tasa sobre ingresos cobrados del mes.
TASAS_RESICO_PF: list[tuple[Decimal, Decimal]] = [
    (Decimal("25000.00"), Decimal("0.0100")),
    (Decimal("50000.00"), Decimal("0.0110")),
    (Decimal("83333.33"), Decimal("0.0150")),
    (Decimal("208333.33"), Decimal("0.0200")),
    (Decimal("3500000.00"), Decimal("0.0250")),
]

REGIMENES_PM_GENERAL = {"601", "603"}
REGIMENES_RESICO = {"626"}
REGIMENES_PF_ACTIVIDAD = {"612", "606", "621"}  # actividad empresarial/profesional, arrendamiento, RIF


def clasificar_regimen(*, tipo_persona: str, regimen_codigo: str | None) -> str:
    """Devuelve la 'mecánica' de ISR aplicable:
    pm_general | pm_resico | pf_resico | pf_actividad | no_aplica"""
    codigo = (regimen_codigo or "").strip()
    if codigo in REGIMENES_RESICO:
        return "pf_resico" if tipo_persona == "fisica" else "pm_resico"
    if tipo_persona == "moral":
        return "pm_general"
    if codigo in REGIMENES_PF_ACTIVIDAD or not codigo:
        return "pf_actividad"
    if codigo == "605":  # sueldos y salarios: el ISR lo retiene el patrón
        return "no_aplica"
    return "pf_actividad"


def isr_tarifa_art96(base: Decimal, *, meses: int = 1) -> Decimal:
    """Aplica la tarifa del art. 96 acumulada a `meses` (límites y cuota × meses),
    como se hace en pagos provisionales de PF (art. 106)."""
    base = Decimal(base)
    if base <= 0:
        return Decimal("0")
    for li, ls, cuota, pct in TARIFA_MENSUAL_ART96:
        # El primer renglón siempre arranca en 0.01; los demás límites y la
        # cuota fija se multiplican por el número de meses acumulados.
        li_m = li if li == Decimal("0.01") else li * meses
        ls_m = ls * meses if ls is not None else None
        cuota_m = cuota * meses
        if ls_m is None or base <= ls_m:
            return q2((base - li_m) * pct + cuota_m)
    return Decimal("0")


def tasa_resico_pf(ingresos_mes: Decimal) -> Decimal:
    for limite, tasa in TASAS_RESICO_PF:
        if ingresos_mes <= limite:
            return tasa
    return TASAS_RESICO_PF[-1][1]  # rebasa 3.5 MDP: ya no aplica RESICO, se avisa aparte


# ---------------------------------------------------------------------------
# IVA base flujo
# ---------------------------------------------------------------------------


@dataclass
class DesgloseIva:
    """Una fila de la tabla 'PUE / REP / PPD pendiente / no considerados'."""

    concepto: str
    num_cfdis: int = 0
    base: Decimal = Decimal("0")
    iva: Decimal = Decimal("0")


@dataclass
class ResultadoIva:
    trasladado_cobrado: Decimal  # IVA de ingresos PUE + REP emitidos (efectivamente cobrado)
    acreditable_pagado: Decimal  # IVA de gastos PUE + REP recibidos (efectivamente pagado)
    trasladado_ppd_pendiente: Decimal  # facturado PPD sin complemento (cuentas por cobrar)
    acreditable_ppd_pendiente: Decimal  # recibido PPD sin complemento (cuentas por pagar)
    emitidas: list[DesgloseIva] = field(default_factory=list)
    recibidas: list[DesgloseIva] = field(default_factory=list)

    @property
    def saldo(self) -> Decimal:
        """> 0 a cargo · < 0 a favor."""
        return q2(self.trasladado_cobrado - self.acreditable_pagado)


FILAS_IVA = ("PUE", "REP", "Notas de crédito", "PPD pendiente", "No considerados")


def iva_base_flujo(cfdis, pagado_por_uuid: dict[str, tuple[Decimal, Decimal]] | None = None) -> ResultadoIva:
    """`cfdis`: iterable con tipo, direccion, estatus, metodo_pago_codigo, subtotal, iva, uuid_fiscal.
    `pagado_por_uuid`: {uuid factura PPD: (importe pagado, IVA pagado)} según los
    complementos de pago reales — lo ya pagado deja de ser "PPD pendiente"."""
    pagado_por_uuid = pagado_por_uuid or {}
    filas_e = {k: DesgloseIva(k) for k in FILAS_IVA}
    filas_r = {k: DesgloseIva(k) for k in FILAS_IVA}

    def suma(fila: DesgloseIva, c, base=None, iva=None) -> None:
        fila.num_cfdis += 1
        fila.base += Decimal(c.subtotal) if base is None else base
        fila.iva += Decimal(c.iva) if iva is None else iva

    for c in cfdis:
        if c.tipo in ("nomina", "traslado"):
            continue  # sin IVA
        filas = filas_e if c.direccion == "emitido" else filas_r
        if c.estatus != "vigente":
            suma(filas["No considerados"], c)
        elif c.tipo == "pago":
            suma(filas["REP"], c)
        elif c.tipo == "nota_credito":
            suma(filas["Notas de crédito"], c)
        elif c.metodo_pago_codigo == "PPD":
            pagado, iva_pagado = pagado_por_uuid.get(getattr(c, "uuid_fiscal", ""), (Decimal("0"), Decimal("0")))
            total = Decimal(c.subtotal) + Decimal(c.iva)
            if pagado >= total and total > 0:
                continue  # totalmente pagada: ya está en los REP
            base_pend = max(Decimal(c.subtotal) - (pagado - iva_pagado), Decimal("0"))
            iva_pend = max(Decimal(c.iva) - iva_pagado, Decimal("0"))
            suma(filas["PPD pendiente"], c, base_pend, iva_pend)
        else:
            suma(filas["PUE"], c)

    tras = filas_e["PUE"].iva + filas_e["REP"].iva - filas_e["Notas de crédito"].iva
    acre = filas_r["PUE"].iva + filas_r["REP"].iva - filas_r["Notas de crédito"].iva
    for f in list(filas_e.values()) + list(filas_r.values()):
        f.base, f.iva = q2(f.base), q2(f.iva)
    return ResultadoIva(
        trasladado_cobrado=q2(tras),
        acreditable_pagado=q2(acre),
        trasladado_ppd_pendiente=q2(filas_e["PPD pendiente"].iva),
        acreditable_ppd_pendiente=q2(filas_r["PPD pendiente"].iva),
        emitidas=list(filas_e.values()),
        recibidas=list(filas_r.values()),
    )


# ---------------------------------------------------------------------------
# ISR provisional
# ---------------------------------------------------------------------------


@dataclass
class MesIsr:
    mes: int
    ingresos_mes: Decimal
    deducciones_mes: Decimal
    ingresos_acumulados: Decimal
    deducciones_acumuladas: Decimal
    base: Decimal  # utilidad fiscal estimada / base gravable acumulada
    isr_acumulado: Decimal
    pagos_anteriores: Decimal
    isr_del_mes: Decimal  # pago provisional del mes
    tasa_aplicada: Decimal | None = None


@dataclass
class ResultadoIsr:
    mecanica: str
    descripcion: str
    meses: list[MesIsr]
    advertencias: list[str] = field(default_factory=list)


def _acumular(meses: list[MesIsr]) -> None:
    ing = ded = Decimal("0")
    for m in meses:
        ing += m.ingresos_mes
        ded += m.deducciones_mes
        m.ingresos_acumulados, m.deducciones_acumuladas = q2(ing), q2(ded)


def isr_provisional(
    *,
    mecanica: str,
    ingresos_por_mes: dict[int, Decimal],
    deducciones_por_mes: dict[int, Decimal],
    hasta_mes: int,
    coeficiente_utilidad: Decimal | None,
) -> ResultadoIsr:
    """Calcula los pagos provisionales de enero a `hasta_mes` del ejercicio.

    ingresos_por_mes / deducciones_por_mes: montos SIN IVA. Para PM general los
    ingresos son nominales (facturados); para el resto, cobrados/pagados (flujo).
    """
    adv: list[str] = []
    meses = [
        MesIsr(
            mes=m,
            ingresos_mes=q2(ingresos_por_mes.get(m, Decimal("0"))),
            deducciones_mes=q2(deducciones_por_mes.get(m, Decimal("0"))),
            ingresos_acumulados=Decimal("0"),
            deducciones_acumuladas=Decimal("0"),
            base=Decimal("0"),
            isr_acumulado=Decimal("0"),
            pagos_anteriores=Decimal("0"),
            isr_del_mes=Decimal("0"),
        )
        for m in range(1, hasta_mes + 1)
    ]
    _acumular(meses)

    if mecanica == "no_aplica":
        return ResultadoIsr(
            mecanica, "Régimen de sueldos y salarios: el ISR lo retiene y entera el patrón.", meses, adv
        )

    if mecanica == "pm_general":
        cu = coeficiente_utilidad or Decimal("0")
        if not coeficiente_utilidad:
            adv.append(
                "No hay coeficiente de utilidad configurado para la empresa; el ISR estimado sale en 0. "
                "Captúralo en Configuración fiscal (art. 14 LISR: utilidad fiscal ÷ ingresos nominales del ejercicio anterior)."
            )
        acumulado_anterior = Decimal("0")
        for m in meses:
            m.base = q2(m.ingresos_acumulados * cu)
            m.isr_acumulado = q2(m.base * TASA_ISR_PM)
            m.pagos_anteriores = acumulado_anterior
            m.isr_del_mes = q2(max(m.isr_acumulado - acumulado_anterior, Decimal("0")))
            m.tasa_aplicada = TASA_ISR_PM
            acumulado_anterior = max(m.isr_acumulado, acumulado_anterior)
        desc = f"Persona moral (régimen general): ingresos nominales acumulados × coeficiente de utilidad {cu} × 30 %, menos pagos provisionales anteriores."
        return ResultadoIsr(mecanica, desc, meses, adv)

    if mecanica == "pm_resico":
        acumulado_anterior = Decimal("0")
        for m in meses:
            m.base = q2(max(m.ingresos_acumulados - m.deducciones_acumuladas, Decimal("0")))
            m.isr_acumulado = q2(m.base * TASA_ISR_PM)
            m.pagos_anteriores = acumulado_anterior
            m.isr_del_mes = q2(max(m.isr_acumulado - acumulado_anterior, Decimal("0")))
            m.tasa_aplicada = TASA_ISR_PM
            acumulado_anterior = max(m.isr_acumulado, acumulado_anterior)
        desc = "Persona moral RESICO: (ingresos efectivamente cobrados − deducciones pagadas) acumulados × 30 %, menos pagos anteriores."
        return ResultadoIsr(mecanica, desc, meses, adv)

    if mecanica == "pf_resico":
        for m in meses:
            tasa = tasa_resico_pf(m.ingresos_mes)
            m.base = m.ingresos_mes
            m.tasa_aplicada = tasa
            m.isr_del_mes = q2(m.ingresos_mes * tasa)
            m.isr_acumulado = q2(sum((x.isr_del_mes for x in meses if x.mes <= m.mes), Decimal("0")))
            m.pagos_anteriores = q2(m.isr_acumulado - m.isr_del_mes)
        if any(x.ingresos_acumulados > Decimal("3500000") for x in meses):
            adv.append("Los ingresos acumulados rebasan $3,500,000: la persona física dejaría de tributar en RESICO.")
        desc = "Persona física RESICO: tasa del 1 % al 2.5 % sobre los ingresos efectivamente cobrados de cada mes (sin deducciones)."
        return ResultadoIsr(mecanica, desc, meses, adv)

    # pf_actividad (empresarial y profesional / arrendamiento): tarifa art. 96 acumulada
    acumulado_anterior = Decimal("0")
    for m in meses:
        m.base = q2(max(m.ingresos_acumulados - m.deducciones_acumuladas, Decimal("0")))
        m.isr_acumulado = isr_tarifa_art96(m.base, meses=m.mes)
        m.pagos_anteriores = acumulado_anterior
        m.isr_del_mes = q2(max(m.isr_acumulado - acumulado_anterior, Decimal("0")))
        acumulado_anterior = max(m.isr_acumulado, acumulado_anterior)
    desc = "Persona física con actividad empresarial/profesional: (ingresos cobrados − deducciones pagadas) acumulados, tarifa del art. 96 acumulada al mes, menos pagos anteriores."
    return ResultadoIsr(mecanica, desc, meses, adv)
