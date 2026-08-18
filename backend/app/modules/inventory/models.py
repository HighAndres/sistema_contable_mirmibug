"""Inventario con patrón de ledger: el stock nunca se guarda como número mutable,
es la suma de un histórico de movimientos con signo (mismo patrón que aura_shop:
app/models/inventory.py), simplificado sin variantes/lotes porque nubinox no es
e-commerce (un producto = una fila, no SKU por variante de talla/color).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class Almacen(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "almacenes"
    __table_args__ = (UniqueConstraint("empresa_id", "codigo", name="uq_almacen_empresa_codigo"),)

    empresa_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("empresas.id", ondelete="CASCADE"), index=True, nullable=False
    )
    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    codigo: Mapped[str] = mapped_column(String(40), nullable=False)
    activo: Mapped[bool] = mapped_column(default=True, nullable=False)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Almacen {self.codigo}>"


class Producto(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "productos"
    __table_args__ = (UniqueConstraint("empresa_id", "sku", name="uq_producto_empresa_sku"),)

    empresa_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("empresas.id", ondelete="CASCADE"), index=True, nullable=False
    )
    sku: Mapped[str] = mapped_column(String(64), nullable=False)
    nombre: Mapped[str] = mapped_column(String(255), nullable=False)
    # "producto" (con stock) | "servicio" (no se controla existencia).
    tipo: Mapped[str] = mapped_column(String(20), default="producto", server_default="producto", nullable=False)
    # Texto libre, no un catálogo cerrado: cada empresa nombra sus propias
    # categorías (p. ej. "Cómputo", "Mobiliario", "Consultoría"...).
    categoria: Mapped[str | None] = mapped_column(String(80), index=True)
    unidad_codigo: Mapped[str | None] = mapped_column(String(10))
    costo_unitario: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    # Atributos libres clave/valor (p. ej. {"color": "negro", "talla": "M"}),
    # para que el mismo modelo se adapte a cualquier giro sin migraciones nuevas.
    atributos: Mapped[dict | None] = mapped_column(JSON)
    # Clave del catálogo c_ClaveProdServ del SAT (para facturar el producto).
    clave_prodserv: Mapped[str | None] = mapped_column(String(10))
    activo: Mapped[bool] = mapped_column(default=True, nullable=False)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Producto {self.sku}>"


class StockMovimiento(UUIDPKMixin, Base):
    __tablename__ = "stock_movimientos"
    __table_args__ = (CheckConstraint("cantidad <> 0", name="ck_movimiento_cantidad_no_cero"),)

    empresa_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("empresas.id", ondelete="CASCADE"), index=True, nullable=False
    )
    producto_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("productos.id", ondelete="CASCADE"), index=True, nullable=False
    )
    almacen_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("almacenes.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    tipo: Mapped[str] = mapped_column(String(20), nullable=False)  # entrada | salida | ajuste
    cantidad: Mapped[int] = mapped_column(Integer, nullable=False)  # con signo
    referencia: Mapped[str | None] = mapped_column(String(120))
    nota: Mapped[str | None] = mapped_column(String(255))
    # Costo unitario con el que entró/salió esta capa (landed cost cuando viene
    # de un pedimento). Nulo en movimientos históricos o ajustes sin costo.
    costo_unitario: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    fecha: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    producto: Mapped[Producto] = relationship(lazy="selectin")
    almacen: Mapped[Almacen] = relationship(lazy="selectin")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<StockMovimiento producto={self.producto_id} cantidad={self.cantidad}>"
