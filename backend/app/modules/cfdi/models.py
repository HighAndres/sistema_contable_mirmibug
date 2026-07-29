"""CFDI (Comprobante Fiscal Digital por Internet) emitido o recibido.

Los datos son generados/sincronizados (reales o simulados vía el módulo sat),
nunca capturados a mano: por eso no hay endpoints de creación manual aquí.
"""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import Date, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class Cfdi(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "cfdis"

    empresa_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("empresas.id", ondelete="CASCADE"), index=True, nullable=False
    )
    uuid_fiscal: Mapped[str] = mapped_column(String(36), unique=True, index=True, nullable=False)
    tipo: Mapped[str] = mapped_column(String(10), nullable=False)  # ingreso | egreso | pago | nomina
    direccion: Mapped[str] = mapped_column(String(10), nullable=False)  # emitido | recibido

    rfc_emisor: Mapped[str] = mapped_column(String(13), index=True, nullable=False)
    nombre_emisor: Mapped[str] = mapped_column(String(255), nullable=False)
    rfc_receptor: Mapped[str] = mapped_column(String(13), index=True, nullable=False)
    nombre_receptor: Mapped[str] = mapped_column(String(255), nullable=False)

    forma_pago_codigo: Mapped[str | None] = mapped_column(String(5))
    uso_cfdi_codigo: Mapped[str | None] = mapped_column(String(5))

    subtotal: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    iva: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    total: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)

    fecha: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    estatus: Mapped[str] = mapped_column(String(15), default="vigente", nullable=False)  # vigente | cancelado

    conceptos: Mapped[list["CfdiConcepto"]] = relationship(
        back_populates="cfdi", cascade="all, delete-orphan", lazy="selectin"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Cfdi {self.uuid_fiscal}>"


class CfdiConcepto(UUIDPKMixin, Base):
    __tablename__ = "cfdi_conceptos"

    cfdi_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("cfdis.id", ondelete="CASCADE"), index=True, nullable=False
    )
    descripcion: Mapped[str] = mapped_column(String(255), nullable=False)
    cantidad: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False)
    unidad_codigo: Mapped[str | None] = mapped_column(String(10))
    valor_unitario: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False)
    importe: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)

    cfdi: Mapped[Cfdi] = relationship(back_populates="conceptos")
