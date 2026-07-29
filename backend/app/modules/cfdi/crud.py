import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.cfdi.models import Cfdi


def get(db: Session, *, empresa_id: uuid.UUID, cfdi_id: uuid.UUID) -> Cfdi | None:
    return db.scalar(
        select(Cfdi).where(Cfdi.id == cfdi_id, Cfdi.empresa_id == empresa_id)
    )


def list_paginado(
    db: Session,
    *,
    empresa_id: uuid.UUID,
    tipo: str | None = None,
    direccion: str | None = None,
    estatus: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Cfdi], int]:
    stmt = select(Cfdi).where(Cfdi.empresa_id == empresa_id)
    if tipo:
        stmt = stmt.where(Cfdi.tipo == tipo)
    if direccion:
        stmt = stmt.where(Cfdi.direccion == direccion)
    if estatus:
        stmt = stmt.where(Cfdi.estatus == estatus)

    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    items = list(
        db.scalars(stmt.order_by(Cfdi.fecha.desc()).limit(limit).offset(offset))
    )
    return items, total
