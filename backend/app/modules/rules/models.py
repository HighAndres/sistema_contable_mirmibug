"""Catálogo de reglas de validación fiscal y las alertas que generan sobre un CFDI."""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class ReglaValidacion(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "reglas_validacion"

    codigo: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    descripcion: Mapped[str] = mapped_column(String(255), nullable=False)
    severidad: Mapped[str] = mapped_column(String(10), default="media", nullable=False)  # baja | media | alta

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ReglaValidacion {self.codigo}>"


class CfdiAlerta(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "cfdi_alertas"

    cfdi_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("cfdis.id", ondelete="CASCADE"), index=True, nullable=False
    )
    regla_codigo: Mapped[str] = mapped_column(String(50), nullable=False)
    severidad: Mapped[str] = mapped_column(String(10), nullable=False)
    detalle: Mapped[str] = mapped_column(String(500), nullable=False)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<CfdiAlerta cfdi={self.cfdi_id} regla={self.regla_codigo}>"
