import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.credentials.models import CredencialSat


def get_por_empresa(db: Session, empresa_id: uuid.UUID) -> CredencialSat | None:
    return db.scalar(select(CredencialSat).where(CredencialSat.empresa_id == empresa_id))


def conectar(db: Session, *, empresa_id: uuid.UUID, tipo: str) -> CredencialSat:
    """Simula la conexión con el SAT: no valida credenciales reales."""
    credencial = get_por_empresa(db, empresa_id)
    if credencial is None:
        credencial = CredencialSat(empresa_id=empresa_id, tipo=tipo)
        db.add(credencial)

    credencial.tipo = tipo
    credencial.estado = "conectado"
    credencial.conectado_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(credencial)
    return credencial
