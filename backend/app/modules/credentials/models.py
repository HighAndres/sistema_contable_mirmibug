"""Estado de conexión con el SAT por empresa (simulado para la demo).

No se guarda ningún secreto real (CIEC/e.firma) — solo el estado de la
conexión simulada que dispara el botón "Conectar SAT" en el frontend.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, String
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

    # Vigencia de los certificados (simulada: se fija al "conectar"). Con la
    # conexión real vendrían del propio .cer de la e.firma y del CSD.
    fiel_numero_serie: Mapped[str | None] = mapped_column(String(40))
    fiel_vigencia_hasta: Mapped[date | None] = mapped_column(Date)
    csd_numero_serie: Mapped[str | None] = mapped_column(String(40))
    csd_vigencia_hasta: Mapped[date | None] = mapped_column(Date)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<CredencialSat empresa={self.empresa_id} estado={self.estado}>"
