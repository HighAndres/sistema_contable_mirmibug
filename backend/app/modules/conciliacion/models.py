"""Conciliación: cuentas bancarias, movimientos del estado de cuenta y lo declarado
al SAT por periodo. Con esto el resumen compara tres fuentes: lo que hay en la
bóveda de CFDI (SAT), lo que pasó por el banco y lo que se declaró."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class CuentaBancaria(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "cuentas_bancarias"
    __table_args__ = (UniqueConstraint("empresa_id", "alias", name="uq_cuenta_empresa_alias"),)

    empresa_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("empresas.id", ondelete="CASCADE"), index=True, nullable=False)
    banco: Mapped[str] = mapped_column(String(60), nullable=False)
    alias: Mapped[str] = mapped_column(String(60), nullable=False)  # "BBVA principal"
    numero: Mapped[str | None] = mapped_column(String(30))  # últimos dígitos / CLABE
    moneda: Mapped[str] = mapped_column(String(3), default="MXN", server_default="MXN", nullable=False)
    activo: Mapped[bool] = mapped_column(default=True, nullable=False)


class MovimientoBancario(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "movimientos_bancarios"
    __table_args__ = (
        # Evita importar dos veces la misma fila del estado de cuenta.
        UniqueConstraint("cuenta_id", "huella", name="uq_movimiento_cuenta_huella"),
    )

    empresa_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("empresas.id", ondelete="CASCADE"), index=True, nullable=False)
    cuenta_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cuentas_bancarias.id", ondelete="CASCADE"), index=True, nullable=False)
    fecha: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    concepto: Mapped[str] = mapped_column(String(300), nullable=False)
    referencia: Mapped[str | None] = mapped_column(String(80))
    cargo: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)  # salida de dinero
    abono: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)  # entrada de dinero
    saldo: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    # sha1 de (fecha, concepto, referencia, cargo, abono, saldo, fila) para deduplicar importaciones.
    huella: Mapped[str] = mapped_column(String(40), nullable=False)
    fila_origen: Mapped[int | None] = mapped_column(Integer)
    archivo_nombre: Mapped[str | None] = mapped_column(String(120))

    # pendiente | conciliado | ignorado
    estado: Mapped[str] = mapped_column(String(12), default="pendiente", server_default="pendiente", index=True, nullable=False)
    cfdi_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("cfdis.id", ondelete="SET NULL"), index=True)
    # auto | manual — cómo se concilió
    conciliado_por: Mapped[str | None] = mapped_column(String(10))
    nota: Mapped[str | None] = mapped_column(String(255))

    cuenta: Mapped[CuentaBancaria] = relationship(lazy="selectin")
    cfdi = relationship("Cfdi", lazy="selectin")

    @property
    def importe(self) -> Decimal:
        """Con signo: abono positivo, cargo negativo."""
        return Decimal(self.abono or 0) - Decimal(self.cargo or 0)


class DeclaracionPeriodo(UUIDPKMixin, TimestampMixin, Base):
    """Lo que efectivamente se presentó al SAT en el periodo (captura del contador)."""

    __tablename__ = "declaraciones_periodo"
    __table_args__ = (UniqueConstraint("empresa_id", "anio", "mes", name="uq_declaracion_empresa_periodo"),)

    empresa_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("empresas.id", ondelete="CASCADE"), index=True, nullable=False)
    anio: Mapped[int] = mapped_column(Integer, nullable=False)
    mes: Mapped[int] = mapped_column(Integer, nullable=False)
    ingresos_declarados: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    deducciones_declaradas: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    iva_declarado: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))  # a cargo (+) / a favor (−)
    isr_declarado: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    fecha_presentacion: Mapped[date | None] = mapped_column(Date)
    numero_operacion: Mapped[str | None] = mapped_column(String(40))
    notas: Mapped[str | None] = mapped_column(String(500))
