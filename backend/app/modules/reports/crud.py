import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Select, case, extract, func, select
from sqlalchemy.orm import Session

from app.modules.cfdi.models import Cfdi
from app.modules.impuestos import crud as impuestos_crud
from app.modules.reports.schemas import AlertaRegla, CuentasPendientes, DashboardKPIs, MesMonto, TopContraparte
from app.modules.rules.models import CfdiAlerta, ReglaValidacion
from app.modules.tenants.models import Empresa

# Descripción de cada regla para explicar en el dashboard "qué es una alerta de validación".
DESCRIPCION_REGLAS = {
    "efos_detectado": "El RFC de la contraparte aparece en la lista de EFOS (art. 69-B): operaciones presuntamente inexistentes.",
    "descuadre_subtotal": "La suma de los conceptos no coincide con el subtotal del comprobante.",
    "complemento_pago_pendiente": "Factura 'por definir' (99) con más de 30 días sin complemento de pago.",
}


def _periodo(stmt: Select, anio: int | None, mes: int | None) -> Select:
    if anio:
        stmt = stmt.where(extract("year", Cfdi.fecha) == anio)
    if mes:
        stmt = stmt.where(extract("month", Cfdi.fecha) == mes)
    return stmt


def _cuentas_pendientes(db: Session, *, empresa_id: uuid.UUID, tipo: str, anio: int | None, mes: int | None) -> CuentasPendientes:
    """Facturas PPD vigentes del periodo menos lo ya pagado con complementos (REP)."""
    stmt = _periodo(
        select(Cfdi.uuid_fiscal, Cfdi.subtotal, Cfdi.iva, Cfdi.total).where(
            Cfdi.empresa_id == empresa_id, Cfdi.tipo == tipo, Cfdi.estatus == "vigente", Cfdi.metodo_pago_codigo == "PPD"
        ),
        anio,
        mes,
    )
    pagado = impuestos_crud.pagado_por_uuid(db, empresa_id=empresa_id)
    n = 0
    sub = iva = tot = Decimal("0")
    for u, s_, i_, t_ in db.execute(stmt).all():
        p, ip = pagado.get(u, (Decimal("0"), Decimal("0")))
        rest_total = Decimal(t_) - p
        if rest_total <= 0:
            continue
        n += 1
        tot += rest_total
        iva += max(Decimal(i_) - ip, Decimal("0"))
        sub += max(Decimal(s_) - (p - ip), Decimal("0"))
    return CuentasPendientes(num_cfdis=n, subtotal=float(sub), iva=float(iva), total=float(tot))


def dashboard_kpis(db: Session, *, empresa: Empresa, anio: int | None = None, mes: int | None = None) -> DashboardKPIs:
    """KPIs del periodo. anio=None → histórico completo (comportamiento anterior)."""
    empresa_id = empresa.id
    hoy = date.today()
    vigentes = _periodo(select(Cfdi).where(Cfdi.empresa_id == empresa_id, Cfdi.estatus == "vigente"), anio, mes).subquery()

    fila = db.execute(
        select(
            func.coalesce(func.sum(case((vigentes.c.tipo == "ingreso", vigentes.c.total), else_=0)), 0).label("ingresos"),
            func.coalesce(func.sum(case((vigentes.c.tipo == "egreso", vigentes.c.total), else_=0)), 0).label("egresos"),
            func.count().label("total_vigentes"),
        )
    ).one()

    ingresos = Decimal(fila.ingresos)
    egresos = Decimal(fila.egresos)
    utilidad = ingresos - egresos

    # IVA / ISR desde el módulo de impuestos (misma lógica que /iva y /isr).
    anio_imp = anio or hoy.year
    iva = impuestos_crud.iva_periodo(db, empresa_id=empresa_id, anio=anio_imp, mes=mes)
    hasta_mes = mes or (hoy.month if anio_imp == hoy.year else 12)
    isr = impuestos_crud.isr_ejercicio(db, empresa=empresa, anio=anio_imp, hasta_mes=hasta_mes)
    ultimo = isr.meses[-1] if isr.meses else None
    isr_estimado = Decimal("0")
    if ultimo is not None:
        isr_estimado = ultimo.isr_del_mes if mes else ultimo.isr_acumulado

    # Alertas: sobre CFDIs del periodo.
    alertas_stmt = _periodo(
        select(CfdiAlerta.regla_codigo, CfdiAlerta.severidad, func.count(func.distinct(CfdiAlerta.cfdi_id)))
        .join(Cfdi, Cfdi.id == CfdiAlerta.cfdi_id)
        .where(Cfdi.empresa_id == empresa_id),
        anio,
        mes,
    ).group_by(CfdiAlerta.regla_codigo, CfdiAlerta.severidad)
    por_regla = db.execute(alertas_stmt).all()
    reglas_db = {r.codigo: r.descripcion for r in db.scalars(select(ReglaValidacion)).all()}
    alertas_por_severidad: dict[str, int] = {}
    alertas_por_regla: list[AlertaRegla] = []
    for codigo, sev, n in por_regla:
        alertas_por_severidad[sev] = alertas_por_severidad.get(sev, 0) + int(n)
        alertas_por_regla.append(
            AlertaRegla(regla_codigo=codigo, descripcion=DESCRIPCION_REGLAS.get(codigo) or reglas_db.get(codigo) or codigo, severidad=sev, cfdis=int(n))
        )
    alertas_por_regla.sort(key=lambda a: -a.cfdis)

    cfdis_con_alertas = db.scalar(
        _periodo(
            select(func.count(func.distinct(CfdiAlerta.cfdi_id))).join(Cfdi, Cfdi.id == CfdiAlerta.cfdi_id).where(Cfdi.empresa_id == empresa_id),
            anio,
            mes,
        )
    ) or 0

    return DashboardKPIs(
        anio=anio_imp,
        mes=mes,
        ingresos_total=float(ingresos),
        egresos_total=float(egresos),
        utilidad=float(utilidad),
        iva_saldo=float(iva.saldo),
        iva_por_pagar=float(iva.saldo),
        isr_estimado=float(isr_estimado),
        isr_mecanica=isr.mecanica,
        flujo_caja=float(utilidad),
        cuentas_por_cobrar=_cuentas_pendientes(db, empresa_id=empresa_id, tipo="ingreso", anio=anio, mes=mes),
        cuentas_por_pagar=_cuentas_pendientes(db, empresa_id=empresa_id, tipo="egreso", anio=anio, mes=mes),
        cfdis_vigentes=fila.total_vigentes,
        cfdis_con_alertas=cfdis_con_alertas,
        alertas_altas=alertas_por_severidad.get("alta", 0),
        alertas_medias=alertas_por_severidad.get("media", 0),
        alertas_bajas=alertas_por_severidad.get("baja", 0),
        alertas_por_regla=alertas_por_regla,
    )


def serie_mensual(db: Session, *, empresa_id: uuid.UUID, meses: int = 6, anio: int | None = None) -> list[MesMonto]:
    mes_expr = func.to_char(Cfdi.fecha, "YYYY-MM")
    stmt = (
        select(
            mes_expr.label("mes"),
            func.coalesce(func.sum(case((Cfdi.tipo == "ingreso", Cfdi.total), else_=0)), 0),
            func.coalesce(func.sum(case((Cfdi.tipo == "egreso", Cfdi.total), else_=0)), 0),
        )
        .where(Cfdi.empresa_id == empresa_id, Cfdi.estatus == "vigente")
        .group_by(mes_expr)
        .order_by(mes_expr)
    )
    if anio:
        stmt = stmt.where(extract("year", Cfdi.fecha) == anio)
    filas = db.execute(stmt).all()
    serie = [MesMonto(mes=m, ingresos=float(i), egresos=float(e)) for m, i, e in filas]
    return serie if anio else serie[-meses:]


def top_contrapartes(
    db: Session, *, empresa_id: uuid.UUID, direccion: str, limit: int = 5, anio: int | None = None, mes: int | None = None
) -> list[TopContraparte]:
    """direccion='emitido' -> top clientes; direccion='recibido' -> top proveedores."""
    if direccion == "emitido":
        rfc_col, nombre_col = Cfdi.rfc_receptor, Cfdi.nombre_receptor
    else:
        rfc_col, nombre_col = Cfdi.rfc_emisor, Cfdi.nombre_emisor

    stmt = _periodo(
        select(rfc_col, nombre_col, func.sum(Cfdi.total), func.count()).where(
            Cfdi.empresa_id == empresa_id,
            Cfdi.direccion == direccion,
            Cfdi.estatus == "vigente",
            Cfdi.tipo.in_(("ingreso", "egreso")),
        ),
        anio,
        mes,
    )
    filas = db.execute(stmt.group_by(rfc_col, nombre_col).order_by(func.sum(Cfdi.total).desc()).limit(limit)).all()
    return [TopContraparte(rfc=rfc, nombre=nombre, monto_total=float(monto), num_cfdis=n) for rfc, nombre, monto, n in filas]
