"""Empresa (RFC/tenant) y la membresía usuario-empresa con su rol.

Un usuario puede pertenecer a varias empresas con un rol distinto en cada una
(ej. administrador en la suya, contador en la de un cliente del despacho).
"""

from __future__ import annotations

import uuid

from decimal import Decimal

from sqlalchemy import Boolean, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class Empresa(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "empresas"

    rfc: Mapped[str] = mapped_column(String(13), unique=True, index=True, nullable=False)
    razon_social: Mapped[str] = mapped_column(String(255), nullable=False)
    regimen_fiscal_codigo: Mapped[str | None] = mapped_column(String(10))
    # Coeficiente de utilidad (art. 14 LISR) para pagos provisionales de
    # personas morales del régimen general; p. ej. 0.1234. Nulo = no configurado.
    coeficiente_utilidad: Mapped[Decimal | None] = mapped_column(Numeric(7, 4))
    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    @property
    def tipo_persona(self) -> str:
        """'moral' (RFC de 12) o 'fisica' (RFC de 13), como lo define el propio RFC."""
        return "fisica" if len(self.rfc.strip()) == 13 else "moral"

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Empresa {self.rfc}>"


class UsuarioEmpresa(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "usuario_empresas"
    __table_args__ = (UniqueConstraint("usuario_id", "empresa_id", name="uq_usuario_empresa"),)

    usuario_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("usuarios.id", ondelete="CASCADE"), index=True, nullable=False
    )
    empresa_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("empresas.id", ondelete="CASCADE"), index=True, nullable=False
    )
    rol_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("roles.id", ondelete="RESTRICT"), nullable=False
    )

    empresa: Mapped[Empresa] = relationship(lazy="selectin")
    rol = relationship("Rol", lazy="selectin")
    usuario = relationship("Usuario", lazy="selectin")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<UsuarioEmpresa usuario={self.usuario_id} empresa={self.empresa_id}>"
