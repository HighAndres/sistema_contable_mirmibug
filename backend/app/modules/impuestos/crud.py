import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import extract, func, select
from sqlalchemy.orm import Session

from app.modules.cfdi.models import Cfdi, CfdiPagoDocto
from app.modules.impuestos import calculos
from app.modules.tenants.models import Empresa


def cfdis_periodo(db: Session, *, empresa_id: uuid.UUID, anio: int, mes: int | None) -> list[Cfdi]:
    stmt = select(Cfdi).where(Cfdi.empresa_id == empresa_id, extract("year", Cfdi.fecha) == anio)
    if mes:
        stmt = stmt.where(extract("month", Cfdi.fecha) == mes)
    return list(db.scalars(stmt))


def pagado_por_uuid(db: Session, *, empresa_id: uuid.UUID) -> dict[str, tuple[Decimal, Decimal]]:
    """{uuid factura PPD: (importe pagado, IVA pagado)} con los REP vigentes de la empresa."""
    filas = db.execute(
        select(CfdiPagoDocto.uuid_relacionado, func.coalesce(func.sum(CfdiPagoDocto.imp_pagado), 0), func.coalesce(func.sum(CfdiPagoDocto.iva_pagado), 0))
        .join(Cfdi, Cfdi.id == CfdiPagoDocto.cfdi_pago_id)
        .where(Cfdi.empresa_id == empresa_id, Cfdi.estatus == "vigente")
        .group_by(CfdiPagoDocto.uuid_relacionado)
    ).all()
    return {u: (Decimal(p), Decimal(i)) for u, p, i in filas}


def iva_periodo(db: Session, *, empresa_id: uuid.UUID, anio: int, mes: int | None) -> calculos.ResultadoIva:
    return calculos.iva_base_flujo(cfdis_periodo(db, empresa_id=empresa_id, anio=anio, mes=mes), pagado_por_uuid(db, empresa_id=empresa_id))


def _por_mes(db: Session, *, empresa_id: uuid.UUID, anio: int, direccion: str, flujo: bool) -> dict[int, Decimal]:
    """Subtotal (sin IVA) por mes de ingresos (emitidos) o deducciones (recibidos).
    flujo=True: solo lo efectivamente cobrado/pagado (PUE + REP); False: todo lo
    facturado vigente (ingresos nominales, PM general)."""
    mes_expr = extract("month", Cfdi.fecha)
    stmt = (
        select(mes_expr, func.coalesce(func.sum(Cfdi.subtotal), 0))
        .where(
            Cfdi.empresa_id == empresa_id,
            extract("year", Cfdi.fecha) == anio,
            Cfdi.direccion == direccion,
            Cfdi.estatus == "vigente",
            Cfdi.tipo.in_(("ingreso", "egreso", "pago", "nota_credito")),
        )
        .group_by(mes_expr)
    )
    if flujo:
        stmt = stmt.where((Cfdi.tipo.in_(("pago", "nota_credito"))) | (Cfdi.metodo_pago_codigo != "PPD"))
    else:
        # Nominal: facturas de ingreso/egreso; los REP no se vuelven a sumar
        # porque su factura PPD ya cuenta como devengada.
        stmt = stmt.where(Cfdi.tipo.in_(("ingreso", "egreso", "nota_credito")))
    out: dict[int, Decimal] = {}
    for m, v in db.execute(stmt).all():
        out[int(m)] = out.get(int(m), Decimal("0")) + Decimal(v)
    # Las notas de crédito restan (se suman aparte con signo negativo).
    stmt_nc = (
        select(mes_expr, func.coalesce(func.sum(Cfdi.subtotal), 0))
        .where(Cfdi.empresa_id == empresa_id, extract("year", Cfdi.fecha) == anio, Cfdi.direccion == direccion, Cfdi.estatus == "vigente", Cfdi.tipo == "nota_credito")
        .group_by(mes_expr)
    )
    for m, v in db.execute(stmt_nc).all():
        out[int(m)] = out.get(int(m), Decimal("0")) - 2 * Decimal(v)  # estaba sumada; ahora resta
    return out


def isr_ejercicio(db: Session, *, empresa: Empresa, anio: int, hasta_mes: int) -> calculos.ResultadoIsr:
    mecanica = calculos.clasificar_regimen(tipo_persona=empresa.tipo_persona, regimen_codigo=empresa.regimen_fiscal_codigo)
    flujo = mecanica != "pm_general"
    ingresos = _por_mes(db, empresa_id=empresa.id, anio=anio, direccion="emitido", flujo=flujo)
    deducciones = _por_mes(db, empresa_id=empresa.id, anio=anio, direccion="recibido", flujo=True)
    return calculos.isr_provisional(
        mecanica=mecanica,
        ingresos_por_mes=ingresos,
        deducciones_por_mes=deducciones,
        hasta_mes=hasta_mes,
        coeficiente_utilidad=empresa.coeficiente_utilidad,
    )


def anios_con_datos(db: Session, *, empresa_id: uuid.UUID) -> list[int]:
    filas = db.scalars(
        select(extract("year", Cfdi.fecha)).where(Cfdi.empresa_id == empresa_id).distinct().order_by(extract("year", Cfdi.fecha).desc())
    ).all()
    anios = [int(a) for a in filas]
    return anios or [date.today().year]
