"""Estado de conexión con el SAT por empresa (simulado para la demo).

No se guarda ningún secreto real (CIEC/e.firma) — solo el estado de la
conexión simulada que dispara el botón "Conectar SAT" en el frontend.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class CredencialSat(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "credenciales_sat"

    empresa_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("empresas.id", ondelete="CASCADE"), unique=True, index=True, nullable=False
    )
    tipo: Mapped[str] = mapped_column(String(20), nullable=False)  # ciec | efirma
    estado: Mapped[str] = mapped_column(String(20), default="pendiente", nullable=False)  # pendiente | conectado
    conectado_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    def __repr__(self) -> str:  # pragma: no cover
        return f"<CredencialSat empresa={self.empresa_id} estado={self.estado}>"
