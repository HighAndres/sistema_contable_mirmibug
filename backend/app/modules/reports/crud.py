import uuid
from decimal import Decimal

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.modules.cfdi.models import Cfdi
from app.modules.reports.schemas import DashboardKPIs, MesMonto, TopContraparte
from app.modules.rules.models import CfdiAlerta

ISR_TASA_ESTIMADA = Decimal("0.30")


def dashboard_kpis(db: Session, *, empresa_id: uuid.UUID) -> DashboardKPIs:
    vigentes = select(Cfdi).where(Cfdi.empresa_id == empresa_id, Cfdi.estatus == "vigente").subquery()

    fila = db.execute(
        select(
            func.coalesce(
                func.sum(case((vigentes.c.tipo == "ingreso", vigentes.c.total), else_=0)), 0
            ).label("ingresos"),
            func.coalesce(
                func.sum(case((vigentes.c.tipo == "egreso", vigentes.c.total), else_=0)), 0
            ).label("egresos"),
            func.coalesce(
                func.sum(case((vigentes.c.tipo == "ingreso", vigentes.c.iva), else_=0)), 0
            ).label("iva_trasladado"),
            func.coalesce(
                func.sum(case((vigentes.c.tipo == "egreso", vigentes.c.iva), else_=0)), 0
            ).label("iva_acreditable"),
            func.count().label("total_vigentes"),
        )
    ).one()

    ingresos = Decimal(str(fila.ingresos))
    egresos = Decimal(str(fila.egresos))
    utilidad = ingresos - egresos
    iva_por_pagar = Decimal(str(fila.iva_trasladado)) - Decimal(str(fila.iva_acreditable))
    isr_estimado = max(utilidad, Decimal("0")) * ISR_TASA_ESTIMADA

    alertas_por_severidad = dict(
        db.execute(
            select(CfdiAlerta.severidad, func.count(func.distinct(CfdiAlerta.cfdi_id)))
            .join(Cfdi, Cfdi.id == CfdiAlerta.cfdi_id)
            .where(Cfdi.empresa_id == empresa_id)
            .group_by(CfdiAlerta.severidad)
        ).all()
    )

    cfdis_con_alertas = db.scalar(
        select(func.count(func.distinct(CfdiAlerta.cfdi_id)))
        .join(Cfdi, Cfdi.id == CfdiAlerta.cfdi_id)
        .where(Cfdi.empresa_id == empresa_id)
    ) or 0

    return DashboardKPIs(
        ingresos_total=float(ingresos),
        egresos_total=float(egresos),
        utilidad=float(utilidad),
        iva_por_pagar=float(iva_por_pagar),
        isr_estimado=float(isr_estimado),
        flujo_caja=float(utilidad),
        cfdis_vigentes=fila.total_vigentes,
        cfdis_con_alertas=cfdis_con_alertas,
        alertas_altas=alertas_por_severidad.get("alta", 0),
        alertas_medias=alertas_por_severidad.get("media", 0),
        alertas_bajas=alertas_por_severidad.get("baja", 0),
    )


def serie_mensual(db: Session, *, empresa_id: uuid.UUID, meses: int = 6) -> list[MesMonto]:
    mes_expr = func.to_char(Cfdi.fecha, "YYYY-MM")
    filas = db.execute(
        select(
            mes_expr.label("mes"),
            func.coalesce(func.sum(case((Cfdi.tipo == "ingreso", Cfdi.total), else_=0)), 0),
            func.coalesce(func.sum(case((Cfdi.tipo == "egreso", Cfdi.total), else_=0)), 0),
        )
        .where(Cfdi.empresa_id == empresa_id, Cfdi.estatus == "vigente")
        .group_by(mes_expr)
        .order_by(mes_expr)
    ).all()
    return [MesMonto(mes=m, ingresos=float(i), egresos=float(e)) for m, i, e in filas][-meses:]


def top_contrapartes(
    db: Session, *, empresa_id: uuid.UUID, direccion: str, limit: int = 5
) -> list[TopContraparte]:
    """direccion='emitido' -> top clientes; direccion='recibido' -> top proveedores."""
    if direccion == "emitido":
        rfc_col, nombre_col = Cfdi.rfc_receptor, Cfdi.nombre_receptor
    else:
        rfc_col, nombre_col = Cfdi.rfc_emisor, Cfdi.nombre_emisor

    filas = db.execute(
        select(rfc_col, nombre_col, func.sum(Cfdi.total), func.count())
        .where(
            Cfdi.empresa_id == empresa_id,
            Cfdi.direccion == direccion,
            Cfdi.estatus == "vigente",
        )
        .group_by(rfc_col, nombre_col)
        .order_by(func.sum(Cfdi.total).desc())
        .limit(limit)
    ).all()
    return [
        TopContraparte(rfc=rfc, nombre=nombre, monto_total=float(monto), num_cfdis=n)
        for rfc, nombre, monto, n in filas
    ]
