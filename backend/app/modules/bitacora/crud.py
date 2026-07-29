import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.auth.models import Usuario
from app.modules.bitacora.models import Bitacora


def registrar(
    db: Session,
    *,
    empresa_id: uuid.UUID,
    usuario: Usuario,
    accion: str,
    descripcion: str,
    entidad_tipo: str | None = None,
    entidad_id: str | None = None,
    metadatos: dict | None = None,
) -> Bitacora:
    """Escribe una entrada de bitácora. Se llama tras el éxito de la acción principal."""
    entrada = Bitacora(
        empresa_id=empresa_id,
        usuario_id=usuario.id,
        usuario_email=usuario.email,
        accion=accion,
        descripcion=descripcion,
        entidad_tipo=entidad_tipo,
        entidad_id=str(entidad_id) if entidad_id is not None else None,
        metadatos=metadatos,
    )
    db.add(entrada)
    db.commit()
    return entrada


def listar(
    db: Session, *, empresa_id: uuid.UUID, accion: str | None = None, limit: int = 100, offset: int = 0
) -> list[Bitacora]:
    stmt = select(Bitacora).where(Bitacora.empresa_id == empresa_id)
    if accion:
        stmt = stmt.where(Bitacora.accion == accion)
    return list(db.scalars(stmt.order_by(Bitacora.created_at.desc()).limit(limit).offset(offset)))
