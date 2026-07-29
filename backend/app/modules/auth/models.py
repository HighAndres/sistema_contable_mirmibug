"""Modelos de usuario y RBAC (roles/permisos).

A diferencia de un RBAC "global" (usuario -> roles), en nubinox el rol de un
usuario depende de la empresa en la que está operando: el mismo usuario puede
ser "administrador" en una empresa y "contador" (solo lectura de más cosas) en
otra. Por eso Usuario NO tiene una relación directa a Rol aquí — esa relación
vive en tenants.models.UsuarioEmpresa, que además ancla el rol a la empresa.

Rol/Permiso son catálogos globales (compartidos entre empresas), sembrados por
scripts/seed_rbac.py.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Table
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPKMixin

if TYPE_CHECKING:
    pass


rol_permisos = Table(
    "rol_permisos",
    Base.metadata,
    Column("rol_id", ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
    Column("permiso_id", ForeignKey("permisos.id", ondelete="CASCADE"), primary_key=True),
)


class Usuario(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "usuarios"

    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    nombre_completo: Mapped[str | None] = mapped_column(String(255))

    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    # Superadmin: acceso operativo a TODAS las empresas del sistema, sin
    # necesitar una fila en usuario_empresas (ver api/deps.get_current_empresa).
    is_superadmin: Mapped[bool] = mapped_column(default=False, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Bloqueo por intentos fallidos de login (fuerza bruta básica).
    intentos_fallidos: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    bloqueado_hasta: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Se incrementa al cambiar/restablecer la contraseña; se embebe en cada JWT
    # emitido (claim "tv") y se valida en cada request. Así, un access/refresh
    # token robado deja de servir de inmediato en cuanto la contraseña cambia,
    # en vez de seguir siendo válido hasta su expiración natural (hasta 7 días
    # para el refresh token).
    token_version: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Usuario {self.email}>"


class Rol(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "roles"

    nombre: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    descripcion: Mapped[str | None] = mapped_column(String(255))
    es_sistema: Mapped[bool] = mapped_column(default=False, nullable=False)

    permisos: Mapped[list["Permiso"]] = relationship(
        secondary=rol_permisos, back_populates="roles", lazy="selectin"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Rol {self.nombre}>"


class Permiso(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "permisos"

    codigo: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    descripcion: Mapped[str | None] = mapped_column(String(255))

    roles: Mapped[list[Rol]] = relationship(secondary=rol_permisos, back_populates="permisos")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Permiso {self.codigo}>"
