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

    # pendiente | parcial (ligado en parte, falta importe) | conciliado | ignorado
    estado: Mapped[str] = mapped_column(String(12), default="pendiente", server_default="pendiente", index=True, nullable=False)
    # auto | manual — cómo se concilió
    conciliado_por: Mapped[str | None] = mapped_column(String(10))
    nota: Mapped[str | None] = mapped_column(String(255))

    cuenta: Mapped[CuentaBancaria] = relationship(lazy="selectin")
    # Un movimiento puede pagar varios CFDI (1:N) y un CFDI puede cobrarse con
    # varios movimientos (N:1): la relación vive en `conciliacion_ligas`.
    ligas: Mapped[list["LigaConciliacion"]] = relationship(
        back_populates="movimiento", cascade="all, delete-orphan", lazy="selectin", order_by="LigaConciliacion.created_at"
    )

    @property
    def importe(self) -> Decimal:
        """Con signo: abono positivo, cargo negativo."""
        return Decimal(self.abono or 0) - Decimal(self.cargo or 0)

    @property
    def monto(self) -> Decimal:
        """Sin signo: lo que hay que explicar con CFDI."""
        return abs(self.importe)

    @property
    def importe_ligado(self) -> Decimal:
        return sum((Decimal(l.importe) for l in self.ligas), Decimal("0"))

    @property
    def restante(self) -> Decimal:
        return self.monto - self.importe_ligado


class LigaConciliacion(UUIDPKMixin, TimestampMixin, Base):
    """Cuánto de un movimiento bancario se aplica a un CFDI. La suma de ligas de
    un movimiento no puede superar su monto; la suma de ligas de un CFDI (más lo
    pagado por REP) no puede superar el total del CFDI."""

    __tablename__ = "conciliacion_ligas"
    __table_args__ = (UniqueConstraint("movimiento_id", "cfdi_id", name="uq_liga_movimiento_cfdi"),)

    movimiento_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("movimientos_bancarios.id", ondelete="CASCADE"), index=True, nullable=False)
    cfdi_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cfdis.id", ondelete="CASCADE"), index=True, nullable=False)
    importe: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)

    movimiento: Mapped[MovimientoBancario] = relationship(back_populates="ligas")
    cfdi = relationship("Cfdi", lazy="selectin")


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
