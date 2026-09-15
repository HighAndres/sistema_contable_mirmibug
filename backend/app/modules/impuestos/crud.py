import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import and_, extract, func, or_, select
from sqlalchemy.orm import Session, aliased

from app.modules.cfdi.models import Cfdi, CfdiPagoDocto
from app.modules.impuestos import calculos
from app.modules.tenants.models import Empresa


def cfdis_periodo(db: Session, *, empresa_id: uuid.UUID, anio: int, mes: int | None) -> list[Cfdi]:
    stmt = select(Cfdi).where(Cfdi.empresa_id == empresa_id, extract("year", Cfdi.fecha) == anio)
    if mes:
        stmt = stmt.where(extract("month", Cfdi.fecha) == mes)
    return list(db.scalars(stmt))


def pagado_rep_por_uuid(db: Session, *, empresa_id: uuid.UUID) -> dict[str, tuple[Decimal, Decimal]]:
    """{uuid factura PPD: (importe pagado, IVA pagado)} SOLO con los REP vigentes."""
    filas = db.execute(
        select(CfdiPagoDocto.uuid_relacionado, func.coalesce(func.sum(CfdiPagoDocto.imp_pagado), 0), func.coalesce(func.sum(CfdiPagoDocto.iva_pagado), 0))
        .join(Cfdi, Cfdi.id == CfdiPagoDocto.cfdi_pago_id)
        .where(Cfdi.empresa_id == empresa_id, Cfdi.estatus == "vigente")
        .group_by(CfdiPagoDocto.uuid_relacionado)
    ).all()
    return {u: (Decimal(p), Decimal(i)) for u, p, i in filas}


def pagado_por_uuid(db: Session, *, empresa_id: uuid.UUID) -> dict[str, tuple[Decimal, Decimal]]:
    """Como pagado_rep_por_uuid, pero una factura marcada como pagada A MANO
    cuenta como cubierta por completo (total, IVA), para que deje de ser
    "pendiente" en todos lados: IVA base flujo, saldos de clientes/proveedores,
    antigüedad y reportes."""
    return _con_pagos_manuales(db, empresa_id=empresa_id, base=pagado_rep_por_uuid(db, empresa_id=empresa_id))


def _con_pagos_manuales(db: Session, *, empresa_id: uuid.UUID, base: dict[str, tuple[Decimal, Decimal]]) -> dict[str, tuple[Decimal, Decimal]]:
    out = dict(base)
    manuales = db.execute(
        select(Cfdi.uuid_fiscal, Cfdi.total, Cfdi.iva).where(Cfdi.empresa_id == empresa_id, Cfdi.pago_manual_fecha.is_not(None))
    ).all()
    for u, total, iva in manuales:
        p, i = out.get(u, (Decimal("0"), Decimal("0")))
        out[u] = (max(p, Decimal(total)), max(i, Decimal(iva)))
    return out


def pagos_manuales_periodo(db: Session, *, empresa_id: uuid.UUID, anio: int, mes: int | None) -> list[Cfdi]:
    """Facturas PPD vigentes marcadas a mano como pagadas DENTRO del periodo (por
    fecha de pago manual, no por fecha de la factura): en flujo se reconocen ahí."""
    stmt = select(Cfdi).where(Cfdi.empresa_id == empresa_id, Cfdi.estatus == "vigente", extract("year", Cfdi.pago_manual_fecha) == anio)
    if mes:
        stmt = stmt.where(extract("month", Cfdi.pago_manual_fecha) == mes)
    return list(db.scalars(stmt))


def uuids_no_deducibles(db: Session, *, empresa_id: uuid.UUID) -> set[str]:
    """Facturas marcadas por el contador como no deducibles o de deducción
    personal: su IVA no es acreditable, ni el de los REP que las liquidan."""
    return set(
        db.scalars(
            select(Cfdi.uuid_fiscal).where(Cfdi.empresa_id == empresa_id, Cfdi.clasificacion.in_(NO_DEDUCIBLES))
        )
    )


def iva_periodo(db: Session, *, empresa_id: uuid.UUID, anio: int, mes: int | None) -> calculos.ResultadoIva:
    rep = pagado_rep_por_uuid(db, empresa_id=empresa_id)
    return calculos.iva_base_flujo(
        cfdis_periodo(db, empresa_id=empresa_id, anio=anio, mes=mes),
        _con_pagos_manuales(db, empresa_id=empresa_id, base=rep),
        pagos_manuales=pagos_manuales_periodo(db, empresa_id=empresa_id, anio=anio, mes=mes),
        pagado_rep_por_uuid=rep,
        uuids_no_deducibles=uuids_no_deducibles(db, empresa_id=empresa_id),
    )


NO_DEDUCIBLES = ("no_deducible", "deduccion_personal")


def _deducible():
    """Condición para que un gasto reste en el ISR: que el contador no lo haya
    marcado como no deducible ni como deducción personal (esta última se aplica
    en la anual, no en los pagos provisionales).

    Un REP no se clasifica, así que se mira la factura PPD que liquida: si esa
    está marcada como no deducible, el pago tampoco resta. Un REP que liquida
    varias facturas y solo algunas no deducibles se excluye completo — es raro y
    es preferible a deducir de más, pero conviene revisarlo si aparece.
    """
    factura_ppd = aliased(Cfdi)
    liquida_no_deducible = (
        select(CfdiPagoDocto.id)
        .join(factura_ppd, factura_ppd.uuid_fiscal == CfdiPagoDocto.uuid_relacionado)
        .where(CfdiPagoDocto.cfdi_pago_id == Cfdi.id, factura_ppd.clasificacion.in_(NO_DEDUCIBLES))
        .correlate(Cfdi)
        .exists()
    )
    return and_(
        or_(Cfdi.clasificacion.is_(None), Cfdi.clasificacion.not_in(NO_DEDUCIBLES)),
        or_(Cfdi.tipo != "pago", ~liquida_no_deducible),
    )


def _por_mes(db: Session, *, empresa_id: uuid.UUID, anio: int, direccion: str, flujo: bool) -> dict[int, Decimal]:
    """Subtotal (sin IVA) por mes de ingresos (emitidos) o deducciones (recibidos).
    flujo=True: solo lo efectivamente cobrado/pagado (PUE + REP); False: todo lo
    facturado vigente (ingresos nominales, PM general).

    En los gastos se respeta la clasificación del contador: lo marcado como no
    deducible o como deducción personal no entra."""
    mes_expr = extract("month", Cfdi.fecha)
    solo_deducibles = [_deducible()] if direccion == "recibido" else []
    stmt = (
        select(mes_expr, func.coalesce(func.sum(Cfdi.subtotal), 0))
        .where(
            Cfdi.empresa_id == empresa_id,
            extract("year", Cfdi.fecha) == anio,
            Cfdi.direccion == direccion,
            Cfdi.estatus == "vigente",
            Cfdi.tipo.in_(("ingreso", "egreso", "pago", "nota_credito")),
            *solo_deducibles,
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
        .where(Cfdi.empresa_id == empresa_id, extract("year", Cfdi.fecha) == anio, Cfdi.direccion == direccion, Cfdi.estatus == "vigente", Cfdi.tipo == "nota_credito", *solo_deducibles)
        .group_by(mes_expr)
    )
    for m, v in db.execute(stmt_nc).all():
        out[int(m)] = out.get(int(m), Decimal("0")) - 2 * Decimal(v)  # estaba sumada; ahora resta
    if flujo:
        # Facturas PPD pagadas a mano: en flujo se reconocen en el mes del pago
        # manual (los REP ya entran arriba por su propia fecha).
        mes_pm = extract("month", Cfdi.pago_manual_fecha)
        stmt_pm = (
            select(mes_pm, func.coalesce(func.sum(Cfdi.subtotal), 0))
            .where(
                Cfdi.empresa_id == empresa_id,
                extract("year", Cfdi.pago_manual_fecha) == anio,
                Cfdi.direccion == direccion,
                Cfdi.estatus == "vigente",
                Cfdi.tipo.in_(("ingreso", "egreso")),
                Cfdi.metodo_pago_codigo == "PPD",
                *solo_deducibles,
            )
            .group_by(mes_pm)
        )
        for m, v in db.execute(stmt_pm).all():
            out[int(m)] = out.get(int(m), Decimal("0")) + Decimal(v)
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
