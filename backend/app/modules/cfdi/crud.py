import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Select, extract, func, or_, select
from sqlalchemy.orm import Session

from app.modules.cfdi.models import Cfdi

TIPOS = ("ingreso", "egreso", "pago", "nomina", "nota_credito")
ESTATUS = ("vigente", "cancelado", "en_proceso")


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
