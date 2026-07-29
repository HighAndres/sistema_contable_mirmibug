"""Catálogo genérico de listas de referencia (régimen fiscal, forma de pago, etc.).

En vez de una tabla por catálogo, se usa un único modelo (tipo/codigo/nombre)
porque son listas de solo-lectura pequeñas que solo cambian cuando el SAT
publica una nueva versión — no necesitan relaciones propias.
"""

from __future__ import annotations

from sqlalchemy import Boolean, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class Catalogo(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "catalogos"
    __table_args__ = (UniqueConstraint("tipo", "codigo", name="uq_catalogo_tipo_codigo"),)

    tipo: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    codigo: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    nombre: Mapped[str] = mapped_column(String(255), nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Catalogo {self.tipo}:{self.codigo}>"
