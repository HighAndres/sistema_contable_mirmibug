import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Select, and_, extract, func, or_, select
from sqlalchemy.orm import Session, aliased

from app.modules.cfdi.models import Cfdi, CfdiPagoDocto

TIPOS = ("ingreso", "egreso", "pago", "nomina", "nota_credito")
ESTATUS = ("vigente", "cancelado", "en_proceso")
ESTADOS_PAGO = ("pagada", "pendiente")
CLASIFICACIONES = ("deducible", "no_deducible", "deduccion_personal")
# Solo las facturas de gasto/ingreso se clasifican: un REP no es un gasto y
# la nómina se deduce por su propia vía.
TIPOS_CLASIFICABLES = ("ingreso", "egreso", "nota_credito")


def _pagado_rep_subquery(empresa_id: uuid.UUID):
    """Suma de lo pagado por REP vigentes a la factura de la fila (correlacionado por UUID)."""
    rep = aliased(Cfdi)
    return (
        select(func.coalesce(func.sum(CfdiPagoDocto.imp_pagado), 0))
        .join(rep, rep.id == CfdiPagoDocto.cfdi_pago_id)
        .where(rep.empresa_id == empresa_id, rep.estatus == "vigente", CfdiPagoDocto.uuid_relacionado == Cfdi.uuid_fiscal)
        .correlate(Cfdi)
        .scalar_subquery()
    )


def get(db: Session, *, empresa_id: uuid.UUID, cfdi_id: uuid.UUID) -> Cfdi | None:
    return db.scalar(select(Cfdi).where(Cfdi.id == cfdi_id, Cfdi.empresa_id == empresa_id))


def _aplicar_filtros(
    stmt: Select,
    *,
    empresa_id: uuid.UUID,
    tipo: str | None = None,
    direccion: str | None = None,
    estatus: str | None = None,
    emisor: str | None = None,
    receptor: str | None = None,
    anio: int | None = None,
    mes: int | None = None,
    fecha_desde: date | None = None,
    fecha_hasta: date | None = None,
    metodo_pago: str | None = None,
    forma_pago: str | None = None,
    uuid_fiscal: str | None = None,
    q: str | None = None,
    estado_pago: str | None = None,
    clasificacion: str | None = None,
    concepto: str | None = None,
) -> Select:
    stmt = stmt.where(Cfdi.empresa_id == empresa_id)
    if tipo:
        stmt = stmt.where(Cfdi.tipo == tipo)
    if direccion:
        stmt = stmt.where(Cfdi.direccion == direccion)
    if estatus:
        stmt = stmt.where(Cfdi.estatus == estatus)
    if emisor:
        like = f"%{emisor.strip()}%"
        stmt = stmt.where(or_(Cfdi.rfc_emisor.ilike(like), Cfdi.nombre_emisor.ilike(like)))
    if receptor:
        like = f"%{receptor.strip()}%"
        stmt = stmt.where(or_(Cfdi.rfc_receptor.ilike(like), Cfdi.nombre_receptor.ilike(like)))
    if anio:
        stmt = stmt.where(extract("year", Cfdi.fecha) == anio)
    if mes:
        stmt = stmt.where(extract("month", Cfdi.fecha) == mes)
    if fecha_desde:
        stmt = stmt.where(Cfdi.fecha >= fecha_desde)
    if fecha_hasta:
        stmt = stmt.where(Cfdi.fecha <= fecha_hasta)
    if metodo_pago:
        stmt = stmt.where(Cfdi.metodo_pago_codigo == metodo_pago)
    if forma_pago:
        stmt = stmt.where(Cfdi.forma_pago_codigo == forma_pago)
    if uuid_fiscal:
        stmt = stmt.where(Cfdi.uuid_fiscal.ilike(f"%{uuid_fiscal.strip()}%"))
    if estado_pago:
        # Solo aplica a facturas (ingreso/egreso). Una PPD está pagada si se
        # marcó a mano o si los REP cubren el total; PUE se considera pagada
        # al emitirse. Pendiente = PPD vigente sin ninguna de las dos cosas.
        es_factura = Cfdi.tipo.in_(("ingreso", "egreso"))
        ppd_pagada = and_(
            Cfdi.metodo_pago_codigo == "PPD",
            or_(Cfdi.pago_manual_fecha.is_not(None), _pagado_rep_subquery(empresa_id) >= Cfdi.total),
        )
        if estado_pago == "pagada":
            stmt = stmt.where(es_factura, Cfdi.estatus != "cancelado", or_(Cfdi.metodo_pago_codigo != "PPD", ppd_pagada))
        elif estado_pago == "pendiente":
            stmt = stmt.where(es_factura, Cfdi.estatus == "vigente", Cfdi.metodo_pago_codigo == "PPD", ~ppd_pagada)
    if clasificacion:
        if clasificacion == "sin_clasificar":
            stmt = stmt.where(Cfdi.clasificacion.is_(None), Cfdi.tipo.in_(TIPOS_CLASIFICABLES))
        else:
            stmt = stmt.where(Cfdi.clasificacion == clasificacion)
    if concepto:
        stmt = stmt.where(Cfdi.concepto.ilike(f"%{concepto.strip()}%"))
    if q:
        # Búsqueda libre: UUID, serie/folio, RFC o nombre de cualquiera de las partes.
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                Cfdi.uuid_fiscal.ilike(like),
                Cfdi.folio.ilike(like),
                Cfdi.serie.ilike(like),
                Cfdi.rfc_emisor.ilike(like),
                Cfdi.nombre_emisor.ilike(like),
                Cfdi.rfc_receptor.ilike(like),
                Cfdi.nombre_receptor.ilike(like),
            )
        )
    return stmt


def list_paginado(
    db: Session,
    *,
    empresa_id: uuid.UUID,
    limit: int = 50,
    offset: int = 0,
    orden: str = "fecha_desc",
    **filtros,
) -> tuple[list[Cfdi], int]:
    stmt = _aplicar_filtros(select(Cfdi), empresa_id=empresa_id, **filtros)
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    orden_col = {
        "fecha_desc": (Cfdi.fecha.desc(), Cfdi.created_at.desc()),
        "fecha_asc": (Cfdi.fecha.asc(), Cfdi.created_at.asc()),
        "total_desc": (Cfdi.total.desc(),),
        "total_asc": (Cfdi.total.asc(),),
    }.get(orden, (Cfdi.fecha.desc(), Cfdi.created_at.desc()))
    items = list(db.scalars(stmt.order_by(*orden_col).limit(limit).offset(offset)))
    return items, total


def resumen_por_tipo(db: Session, *, empresa_id: uuid.UUID, **filtros) -> dict[str, dict]:
    """Conteo y montos por tipo de comprobante para los filtros dados (sin
    paginar). Solo suma los VIGENTES + en proceso en 'subtotal/iva/total';
    'cancelados' se reporta aparte para que la tarjeta lo muestre."""
    filtros = {k: v for k, v in filtros.items() if k != "tipo"}
    stmt = _aplicar_filtros(
        select(
            Cfdi.tipo,
            func.count().label("n"),
            func.count().filter(Cfdi.estatus == "cancelado").label("cancelados"),
            func.coalesce(func.sum(Cfdi.subtotal).filter(Cfdi.estatus != "cancelado"), 0).label("subtotal"),
            func.coalesce(func.sum(Cfdi.iva).filter(Cfdi.estatus != "cancelado"), 0).label("iva"),
            func.coalesce(func.sum(Cfdi.total).filter(Cfdi.estatus != "cancelado"), 0).label("total"),
            func.count().filter(Cfdi.metodo_pago_codigo == "PPD", Cfdi.estatus != "cancelado").label("ppd"),
        ),
        empresa_id=empresa_id,
        **filtros,
    ).group_by(Cfdi.tipo)
    out = {
        t: {"cantidad": 0, "cancelados": 0, "ppd": 0, "subtotal": 0.0, "iva": 0.0, "total": 0.0} for t in TIPOS
    }
    for tipo, n, canc, subtotal, iva, total, ppd in db.execute(stmt).all():
        out[tipo] = {
            "cantidad": int(n),
            "cancelados": int(canc),
            "ppd": int(ppd),
            "subtotal": float(Decimal(subtotal)),
            "iva": float(Decimal(iva)),
            "total": float(Decimal(total)),
        }
    return out


def anios_disponibles(db: Session, *, empresa_id: uuid.UUID) -> list[int]:
    filas = db.scalars(
        select(extract("year", Cfdi.fecha)).where(Cfdi.empresa_id == empresa_id).distinct().order_by(extract("year", Cfdi.fecha).desc())
    ).all()
    return [int(a) for a in filas]


def pagado_rep_de(db: Session, *, empresa_id: uuid.UUID, uuids: list[str]) -> dict[str, Decimal]:
    """{uuid factura: importe pagado por REP vigentes} solo para los UUID dados
    (una consulta para toda la página de resultados)."""
    if not uuids:
        return {}
    rep = aliased(Cfdi)
    filas = db.execute(
        select(CfdiPagoDocto.uuid_relacionado, func.coalesce(func.sum(CfdiPagoDocto.imp_pagado), 0))
        .join(rep, rep.id == CfdiPagoDocto.cfdi_pago_id)
        .where(rep.empresa_id == empresa_id, rep.estatus == "vigente", CfdiPagoDocto.uuid_relacionado.in_(uuids))
        .group_by(CfdiPagoDocto.uuid_relacionado)
    ).all()
    return {u: Decimal(p) for u, p in filas}


def estado_pago_de(cfdi: Cfdi, pagado_rep: Decimal) -> str | None:
    """pagada | parcial | pendiente para facturas; None para REP, nómina y notas
    de crédito. Una PUE cuenta como pagada al emitirse."""
    if cfdi.tipo not in ("ingreso", "egreso"):
        return None
    if cfdi.metodo_pago_codigo != "PPD" or cfdi.pagada_manualmente:
        return "pagada"
    if pagado_rep >= Decimal(cfdi.total) and cfdi.total > 0:
        return "pagada"
    return "parcial" if pagado_rep > 0 else "pendiente"


def marcar_pago_manual(db: Session, *, cfdi: Cfdi, fecha: date, nota: str | None, usuario_id: uuid.UUID, pagado_rep: Decimal) -> Cfdi:
    """Marca una factura PPD vigente como pagada/cobrada a mano.

    Lanza ValueError si no es una factura PPD vigente o si los REP ya la
    cubren por completo (en ese caso no hay nada que marcar)."""
    if cfdi.tipo not in ("ingreso", "egreso"):
        raise ValueError("Solo se pueden marcar facturas de ingreso o gasto")
    if cfdi.metodo_pago_codigo != "PPD":
        raise ValueError("Una factura PUE ya cuenta como pagada al emitirse; solo aplica a PPD")
    if cfdi.estatus != "vigente":
        raise ValueError("La factura no está vigente")
    if pagado_rep >= Decimal(cfdi.total) and cfdi.total > 0:
        raise ValueError("Los complementos de pago ya cubren el total de la factura")
    if fecha < cfdi.fecha:
        raise ValueError("La fecha de pago no puede ser anterior a la fecha de la factura")
    cfdi.pago_manual_fecha = fecha
    cfdi.pago_manual_nota = (nota or "").strip() or None
    cfdi.pago_manual_usuario_id = usuario_id
    db.commit()
    db.refresh(cfdi)
    return cfdi


def quitar_pago_manual(db: Session, *, cfdi: Cfdi) -> Cfdi:
    if not cfdi.pagada_manualmente:
        raise ValueError("La factura no tiene un pago registrado a mano")
    cfdi.pago_manual_fecha = None
    cfdi.pago_manual_nota = None
    cfdi.pago_manual_usuario_id = None
    db.commit()
    db.refresh(cfdi)
    return cfdi


# ---------------------------------------------------------------------------
# Clasificación manual (papel de trabajo del contador)
# ---------------------------------------------------------------------------


def _limpiar(valor: str | None) -> str | None:
    """Quita espacios sobrantes y respeta mayúsculas/minúsculas tal cual se
    capturaron; las búsquedas por concepto son insensibles a may/min."""
    return (valor or "").strip() or None


def clasificar(
    db: Session,
    *,
    cfdi: Cfdi,
    clasificacion: str | None,
    concepto: str | None,
    cuenta_contable: str | None,
    referencia_bancaria: str | None,
) -> Cfdi:
    """Escribe la clasificación completa de un CFDI. Los campos que llegan vacíos
    se limpian: es la edición de una fila del papel de trabajo, no un parche."""
    if cfdi.tipo not in TIPOS_CLASIFICABLES:
        raise ValueError("Solo se clasifican facturas de ingreso, gasto o notas de crédito")
    cfdi.clasificacion = clasificacion
    cfdi.concepto = _limpiar(concepto)
    cfdi.cuenta_contable = _limpiar(cuenta_contable)
    cfdi.referencia_bancaria = _limpiar(referencia_bancaria)
    db.commit()
    db.refresh(cfdi)
    return cfdi


def clasificar_masivo(
    db: Session,
    *,
    empresa_id: uuid.UUID,
    cfdi_ids: list[uuid.UUID],
    clasificacion: str | None,
    concepto: str | None,
    cuenta_contable: str | None,
    referencia_bancaria: str | None,
) -> tuple[int, int]:
    """Aplica los campos NO nulos a varios CFDIs. Devuelve (actualizados, omitidos).

    A diferencia de `clasificar`, aquí lo que va en nulo no se toca: así se puede
    marcar el concepto de un lote sin borrarle la cuenta contable a cada uno."""
    cambios = {
        k: v
        for k, v in (
            ("clasificacion", clasificacion),
            ("concepto", _limpiar(concepto)),
            ("cuenta_contable", _limpiar(cuenta_contable)),
            ("referencia_bancaria", _limpiar(referencia_bancaria)),
        )
        if v is not None
    }
    if not cambios:
        raise ValueError("No se indicó ningún campo que aplicar")
    # Sin duplicados: si llegara dos veces el mismo id, `omitidos` mentiría.
    pedidos = list(dict.fromkeys(cfdi_ids))
    encontrados = list(
        db.scalars(select(Cfdi).where(Cfdi.empresa_id == empresa_id, Cfdi.id.in_(pedidos)))
    )
    actualizados = 0
    for cfdi in encontrados:
        if cfdi.tipo not in TIPOS_CLASIFICABLES:
            continue
        for campo, valor in cambios.items():
            setattr(cfdi, campo, valor)
        actualizados += 1
    db.commit()
    return actualizados, len(pedidos) - actualizados


def valores_clasificacion(db: Session, *, empresa_id: uuid.UUID) -> tuple[list[str], list[str], int]:
    """Conceptos y cuentas contables ya usados en la empresa (para autocompletar)
    y cuántas facturas siguen sin clasificar."""
    conceptos = list(
        db.scalars(
            select(Cfdi.concepto)
            .where(Cfdi.empresa_id == empresa_id, Cfdi.concepto.is_not(None))
            .distinct()
            .order_by(Cfdi.concepto)
        )
    )
    cuentas = list(
        db.scalars(
            select(Cfdi.cuenta_contable)
            .where(Cfdi.empresa_id == empresa_id, Cfdi.cuenta_contable.is_not(None))
            .distinct()
            .order_by(Cfdi.cuenta_contable)
        )
    )
    sin_clasificar = db.scalar(
        select(func.count())
        .select_from(Cfdi)
        .where(
            Cfdi.empresa_id == empresa_id,
            Cfdi.clasificacion.is_(None),
            Cfdi.estatus == "vigente",
            Cfdi.tipo.in_(TIPOS_CLASIFICABLES),
        )
    )
    return conceptos, cuentas, int(sin_clasificar or 0)


# ---------------------------------------------------------------------------
# Reportes (layout de los despachos)
# ---------------------------------------------------------------------------

TOPE_REPORTE = 10_000


def filas_reporte(db: Session, *, empresa_id: uuid.UUID, **filtros) -> tuple[list, int]:
    """CFDIs que cumplen los filtros de la lista, con la fecha en que se
    cobraron/pagaron ya resuelta (REP, pago manual o la propia fecha si es PUE).
    Devuelve (filas, total) y corta en TOPE_REPORTE."""
    from app.modules.cfdi.reportes import FilaCfdi

    stmt = _aplicar_filtros(select(Cfdi), empresa_id=empresa_id, **filtros)
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    cfdis = list(db.scalars(stmt.order_by(Cfdi.fecha, Cfdi.uuid_fiscal).limit(TOPE_REPORTE)))

    # Lo liquidado por REP: qué complemento pagó cada factura PPD y cuándo. Si
    # hay varias parcialidades se queda la última, que es la fecha en que la
    # factura terminó de cobrarse.
    uuids = [c.uuid_fiscal for c in cfdis if c.metodo_pago_codigo == "PPD"]
    pagos: dict[str, tuple] = {}
    if uuids:
        rep = aliased(Cfdi)
        filas_rep = db.execute(
            select(CfdiPagoDocto.uuid_relacionado, rep.uuid_fiscal, CfdiPagoDocto.fecha_pago, rep.fecha, CfdiPagoDocto.imp_pagado)
            .join(rep, rep.id == CfdiPagoDocto.cfdi_pago_id)
            .where(rep.empresa_id == empresa_id, rep.estatus == "vigente", CfdiPagoDocto.uuid_relacionado.in_(uuids))
        ).all()
        for u, uuid_rep, fecha_docto, fecha_rep, imp in sorted(filas_rep, key=lambda f: f[2] or f[3]):
            acumulado = (pagos[u][2] if u in pagos else Decimal("0")) + Decimal(imp or 0)
            pagos[u] = (uuid_rep, fecha_docto or fecha_rep, acumulado)

    filas = []
    for c in cfdis:
        fecha_pago, uuid_pago, pagado = None, None, Decimal("0")
        if c.tipo in ("ingreso", "egreso"):
            if c.metodo_pago_codigo == "PPD":
                if c.uuid_fiscal in pagos:
                    uuid_pago, fecha_pago, pagado = pagos[c.uuid_fiscal]
                if c.pago_manual_fecha is not None:
                    fecha_pago, pagado = c.pago_manual_fecha, Decimal(c.total)
            else:
                fecha_pago, pagado = c.fecha, Decimal(c.total)  # PUE: se paga al emitirse
        filas.append(FilaCfdi(cfdi=c, fecha_pago=fecha_pago, uuid_pago=uuid_pago, pagado=pagado))
    return filas, int(total)
