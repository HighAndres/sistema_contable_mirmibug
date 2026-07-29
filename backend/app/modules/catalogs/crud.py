from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.catalogs.models import Catalogo


def list_por_tipo(db: Session, tipo: str) -> list[Catalogo]:
    return list(
        db.scalars(
            select(Catalogo)
            .where(Catalogo.tipo == tipo, Catalogo.activo.is_(True))
            .order_by(Catalogo.codigo)
        )
    )
