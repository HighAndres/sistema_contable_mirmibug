"""Bitácora de auditoría: qué hizo cada usuario y cuándo, por empresa.

Se registra al final de las acciones operativas relevantes (crear empresa,
conectar/sincronizar SAT, movimientos de inventario, altas de catálogo) desde
la capa de router, después de que la acción principal ya tuvo éxito. No se
audita cada GET — solo escrituras con impacto de negocio.
"""

from __future__ import annotations

import uuid

from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class Bitacora(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "bitacora"

    empresa_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("empresas.id", ondelete="CASCADE"), index=True, nullable=False
    )
    usuario_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("usuarios.id", ondelete="SET NULL"), index=True
    )
    usuario_email: Mapped[str] = mapped_column(String(320), nullable=False)

    accion: Mapped[str] = mapped_column(String(50), index=True, nullable=False)  # "recurso.evento"
    descripcion: Mapped[str] = mapped_column(String(500), nullable=False)

    entidad_tipo: Mapped[str | None] = mapped_column(String(50))
    entidad_id: Mapped[str | None] = mapped_column(String(64))
    metadatos: Mapped[dict | None] = mapped_column(JSON)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Bitacora {self.accion} usuario={self.usuario_email}>"
