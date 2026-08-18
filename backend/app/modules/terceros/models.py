"""Terceros: clientes y proveedores de la empresa.

Se crean casi siempre solos, a partir de las contrapartes de los CFDI de la
bóveda (RFC receptor de lo emitido = cliente; RFC emisor de lo recibido =
proveedor). El usuario complementa contacto, condiciones de crédito y notas.
Los importes (facturado, saldo, antigüedad) no se guardan: se calculan de los
CFDI y sus complementos de pago.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class Tercero(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "terceros"
    __table_args__ = (UniqueConstraint("empresa_id", "rfc", name="uq_tercero_empresa_rfc"),)

    empresa_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("empresas.id", ondelete="CASCADE"), index=True, nullable=False)
    rfc: Mapped[str] = mapped_column(String(13), index=True, nullable=False)
    nombre: Mapped[str] = mapped_column(String(255), nullable=False)
    # cliente | proveedor | ambos
    tipo: Mapped[str] = mapped_column(String(10), default="cliente", nullable=False)
    regimen_fiscal_codigo: Mapped[str | None] = mapped_column(String(10))
    codigo_postal: Mapped[str | None] = mapped_column(String(5))
    uso_cfdi_default: Mapped[str | None] = mapped_column(String(5))
    email: Mapped[str | None] = mapped_column(String(320))
    telefono: Mapped[str | None] = mapped_column(String(30))
    contacto: Mapped[str | None] = mapped_column(String(120))
    dias_credito: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    limite_credito: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    notas: Mapped[str | None] = mapped_column(String(500))
    # cfdi (detectado en la bóveda) | manual | excel
    origen: Mapped[str] = mapped_column(String(10), default="manual", server_default="manual", nullable=False)
    activo: Mapped[bool] = mapped_column(default=True, nullable=False)
