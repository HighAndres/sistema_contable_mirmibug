"""CFDI (Comprobante Fiscal Digital por Internet) emitido o recibido.

Los datos son generados/sincronizados (reales o simulados vía el módulo sat),
nunca capturados a mano: por eso no hay endpoints de creación manual aquí.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class Cfdi(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "cfdis"

    empresa_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("empresas.id", ondelete="CASCADE"), index=True, nullable=False
    )
    uuid_fiscal: Mapped[str] = mapped_column(String(36), unique=True, index=True, nullable=False)
    version: Mapped[str | None] = mapped_column(String(5))  # "4.0" | "3.3"
    serie: Mapped[str | None] = mapped_column(String(25))
    folio: Mapped[str | None] = mapped_column(String(40), index=True)
    # ingreso (venta emitida) | egreso (gasto recibido) | pago (REP) | nomina | nota_credito (E)
    tipo: Mapped[str] = mapped_column(String(15), nullable=False)
    # Letra del SAT: I ingreso, E egreso (nota de crédito), P pago, N nómina, T traslado.
    tipo_comprobante: Mapped[str | None] = mapped_column(String(1))
    direccion: Mapped[str] = mapped_column(String(10), nullable=False)  # emitido | recibido

    rfc_emisor: Mapped[str] = mapped_column(String(13), index=True, nullable=False)
    nombre_emisor: Mapped[str] = mapped_column(String(255), nullable=False)
    rfc_receptor: Mapped[str] = mapped_column(String(13), index=True, nullable=False)
    nombre_receptor: Mapped[str] = mapped_column(String(255), nullable=False)

    forma_pago_codigo: Mapped[str | None] = mapped_column(String(5))
    # PUE (una sola exhibición) | PPD (parcialidades o diferido). Nulo en pago/nómina.
    metodo_pago_codigo: Mapped[str | None] = mapped_column(String(5), index=True)
    uso_cfdi_codigo: Mapped[str | None] = mapped_column(String(5))

    # Decimal (no float): montos legales/contables — nada de aritmética binaria
    # de punto flotante entre la generación del CFDI y su almacenamiento.
    subtotal: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    iva: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    total: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)

    fecha: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    fecha_timbrado: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # vigente | cancelado | en_proceso (en proceso de cancelación)
    estatus: Mapped[str] = mapped_column(String(15), default="vigente", nullable=False)
    # mock (simulado) | xml (cargado a mano) | descarga (Web Service del SAT)
    origen: Mapped[str] = mapped_column(String(10), default="mock", server_default="mock", nullable=False)
    # XML original tal cual se recibió (para re-descargar / auditar). Nulo en simulados.
    xml: Mapped[str | None] = mapped_column(Text)
    # Impuestos retenidos (ISR/IVA) — informativos para la previa de IVA/ISR.
    iva_retenido: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, server_default="0", nullable=False)
    isr_retenido: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, server_default="0", nullable=False)

    pagos_relacionados: Mapped[list["CfdiPagoDocto"]] = relationship(
        back_populates="cfdi_pago", cascade="all, delete-orphan", lazy="selectin"
    )

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
    valor_unitario: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    importe: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)

    cfdi: Mapped[Cfdi] = relationship(back_populates="conceptos")


class CfdiPagoDocto(UUIDPKMixin, Base):
    """Documento relacionado dentro de un complemento de pago (REP): qué factura
    PPD se está pagando y cuánto. Es lo que permite saber si una factura PPD ya
    se cobró/pagó (IVA base flujo, cuentas por cobrar/pagar, conciliación)."""

    __tablename__ = "cfdi_pago_doctos"

    cfdi_pago_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cfdis.id", ondelete="CASCADE"), index=True, nullable=False)
    uuid_relacionado: Mapped[str] = mapped_column(String(36), index=True, nullable=False)  # la factura PPD
    serie: Mapped[str | None] = mapped_column(String(25))
    folio: Mapped[str | None] = mapped_column(String(40))
    num_parcialidad: Mapped[int | None] = mapped_column(Integer)
    imp_saldo_anterior: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    imp_pagado: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    imp_saldo_insoluto: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    iva_pagado: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)  # TrasladoDR IVA
    fecha_pago: Mapped[date | None] = mapped_column(Date)
    forma_pago_codigo: Mapped[str | None] = mapped_column(String(5))

    cfdi_pago: Mapped[Cfdi] = relationship(back_populates="pagos_relacionados")
