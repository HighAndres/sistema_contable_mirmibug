"""CFDI (Comprobante Fiscal Digital por Internet) emitido o recibido.

Los datos son generados/sincronizados (reales o simulados vía el módulo sat),
nunca capturados a mano: por eso no hay endpoints de creación manual aquí.
Lo único que se edita a mano es la marca de "pagada" de una factura PPD
(pago_manual_*), para los casos reales en que no existe complemento de pago
ni movimiento bancario identificable y aun así debe contar en impuestos.
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

    # Pago registrado A MANO por el contador (factura PPD sin REP ni movimiento
    # bancario). Con fecha ≠ nulo la factura cuenta como cobrada/pagada en esa
    # fecha para IVA base flujo, ISR en flujo, saldos de terceros y reportes.
    pago_manual_fecha: Mapped[date | None] = mapped_column(Date, index=True)
    pago_manual_nota: Mapped[str | None] = mapped_column(String(255))
    pago_manual_usuario_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuarios.id", ondelete="SET NULL"))

    # Clasificación que el contador captura a mano sobre el CFDI, tal como en su
    # papel de trabajo: qué efecto fiscal tiene el gasto, bajo qué concepto y
    # cuenta contable va, y con qué movimiento bancario se identificó. El XML no
    # trae nada de esto y de ello depende que el ISR y el IVA cuadren: un gasto
    # marcado como no deducible o como deducción personal deja de restar en el
    # pago provisional y su IVA deja de ser acreditable.
    # deducible | no_deducible | deduccion_personal. Nulo = sin clasificar
    # (se considera deducible, que es como venía calculándose).
    clasificacion: Mapped[str | None] = mapped_column(String(20), index=True)
    concepto: Mapped[str | None] = mapped_column(String(60), index=True)  # TELEFONOS, PEAJE, HONORARIOS MEDICOS…
    cuenta_contable: Mapped[str | None] = mapped_column(String(20))  # 6100-039-000
    referencia_bancaria: Mapped[str | None] = mapped_column(String(40))  # "ENE 1061"

    # Datos del comprobante que el XML sí trae y los reportes del contador piden
    # columna por columna (ONEFACTURE / MiAdminPro). Nulos en los CFDI simulados
    # y en los cargados antes de que existieran estas columnas.
    moneda: Mapped[str | None] = mapped_column(String(3))
    tipo_cambio: Mapped[Decimal | None] = mapped_column(Numeric(14, 6))
    descuento: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, server_default="0", nullable=False)
    regimen_emisor: Mapped[str | None] = mapped_column(String(5))
    regimen_receptor: Mapped[str | None] = mapped_column(String(5))
    lugar_expedicion: Mapped[str | None] = mapped_column(String(10))  # CP
    domicilio_receptor: Mapped[str | None] = mapped_column(String(10))  # CP del receptor
    exportacion: Mapped[str | None] = mapped_column(String(10))
    condiciones_pago: Mapped[str | None] = mapped_column(String(80))
    pac_rfc: Mapped[str | None] = mapped_column(String(13))  # quién timbró
    cuenta_predial: Mapped[str | None] = mapped_column(String(150))
    # Complementos incorporados (Pagos, Nomina, ImpuestosLocales…), separados por coma.
    complementos: Mapped[str | None] = mapped_column(String(255))
    # CFDI global (ventas al público en general).
    global_periodicidad: Mapped[str | None] = mapped_column(String(5))
    global_meses: Mapped[str | None] = mapped_column(String(5))
    global_anio: Mapped[str | None] = mapped_column(String(4))
    # Datos de la cancelación. Hoy solo se llenan si la sincronización con el SAT
    # los trae; con el mock quedan nulos.
    fecha_cancelacion: Mapped[date | None] = mapped_column(Date)
    motivo_cancelacion: Mapped[str | None] = mapped_column(String(5))
    folio_sustitucion: Mapped[str | None] = mapped_column(String(36))

    pagos_relacionados: Mapped[list["CfdiPagoDocto"]] = relationship(
        back_populates="cfdi_pago", cascade="all, delete-orphan", lazy="selectin"
    )

    conceptos: Mapped[list["CfdiConcepto"]] = relationship(
        back_populates="cfdi", cascade="all, delete-orphan", lazy="selectin"
    )

    impuestos: Mapped[list["CfdiImpuesto"]] = relationship(
        back_populates="cfdi", cascade="all, delete-orphan", lazy="selectin"
    )

    relacionados: Mapped[list["CfdiRelacionado"]] = relationship(
        back_populates="cfdi", cascade="all, delete-orphan", lazy="selectin"
    )

    nomina: Mapped["CfdiNomina | None"] = relationship(
        back_populates="cfdi", cascade="all, delete-orphan", uselist=False, lazy="selectin"
    )

    @property
    def pagada_manualmente(self) -> bool:
        return self.pago_manual_fecha is not None

    @property
    def deducible(self) -> bool:
        """Si el gasto resta en el ISR y su IVA es acreditable. Sin clasificar
        cuenta como deducible: así se comportaba el sistema antes de existir
        esta captura y no queremos cambiar cifras a espaldas del contador."""
        return self.clasificacion in (None, "deducible")

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
    clave_prodserv: Mapped[str | None] = mapped_column(String(15))
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


class CfdiImpuesto(UUIDPKMixin, Base):
    """Impuesto del comprobante agrupado por tasa.

    Los reportes del despacho piden base e importe de CADA tasa por separado
    ("IVA 16 Base", "IVA 0", "IVA Exento", "IEPS 3 Importe", locales…), cosa que
    no se puede reconstruir del total. Se guarda una fila por combinación de
    naturaleza + impuesto + factor + tasa.
    """

    __tablename__ = "cfdi_impuestos"

    cfdi_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cfdis.id", ondelete="CASCADE"), index=True, nullable=False)
    naturaleza: Mapped[str] = mapped_column(String(10), nullable=False)  # traslado | retencion | no_objeto
    impuesto: Mapped[str] = mapped_column(String(10), nullable=False)  # 001 ISR · 002 IVA · 003 IEPS · local
    tipo_factor: Mapped[str | None] = mapped_column(String(10))  # Tasa | Cuota | Exento
    tasa: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    base: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    importe: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    nombre_local: Mapped[str | None] = mapped_column(String(60))

    cfdi: Mapped[Cfdi] = relationship(back_populates="impuestos")


class CfdiRelacionado(UUIDPKMixin, Base):
    """UUID que este CFDI relaciona (nota de crédito que corrige una factura,
    sustitución de un cancelado, etc.). El reporte lo pide en dos columnas."""

    __tablename__ = "cfdi_relacionados"

    cfdi_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cfdis.id", ondelete="CASCADE"), index=True, nullable=False)
    tipo_relacion: Mapped[str | None] = mapped_column(String(5))
    uuid_relacionado: Mapped[str] = mapped_column(String(36), index=True, nullable=False)

    cfdi: Mapped[Cfdi] = relationship(back_populates="relacionados")


class CfdiNomina(UUIDPKMixin, Base):
    """Complemento de nómina 1.2 del recibo. Uno por CFDI de nómina."""

    __tablename__ = "cfdi_nominas"

    cfdi_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cfdis.id", ondelete="CASCADE"), index=True, unique=True, nullable=False)
    version: Mapped[str | None] = mapped_column(String(5))
    tipo_nomina: Mapped[str | None] = mapped_column(String(5))  # O ordinaria · E extraordinaria
    fecha_pago: Mapped[date | None] = mapped_column(Date, index=True)
    fecha_inicial_pago: Mapped[date | None] = mapped_column(Date)
    fecha_final_pago: Mapped[date | None] = mapped_column(Date)
    num_dias_pagados: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    total_percepciones: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    total_deducciones: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    total_otros_pagos: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    registro_patronal: Mapped[str | None] = mapped_column(String(20))
    curp_emisor: Mapped[str | None] = mapped_column(String(18))
    curp_receptor: Mapped[str | None] = mapped_column(String(18))
    num_seguridad_social: Mapped[str | None] = mapped_column(String(15))
    fecha_inicio_rel_laboral: Mapped[date | None] = mapped_column(Date)
    antiguedad: Mapped[str | None] = mapped_column(String(15))
    tipo_contrato: Mapped[str | None] = mapped_column(String(5))
    sindicalizado: Mapped[str | None] = mapped_column(String(2))
    tipo_jornada: Mapped[str | None] = mapped_column(String(5))
    tipo_regimen: Mapped[str | None] = mapped_column(String(5))
    num_empleado: Mapped[str | None] = mapped_column(String(15))
    departamento: Mapped[str | None] = mapped_column(String(100))
    puesto: Mapped[str | None] = mapped_column(String(100))
    riesgo_puesto: Mapped[str | None] = mapped_column(String(5))
    periodicidad_pago: Mapped[str | None] = mapped_column(String(5))
    banco: Mapped[str | None] = mapped_column(String(10))
    cuenta_bancaria: Mapped[str | None] = mapped_column(String(20))
    salario_base_cot_apor: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    salario_diario_integrado: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    clave_ent_fed: Mapped[str | None] = mapped_column(String(5))

    cfdi: Mapped[Cfdi] = relationship(back_populates="nomina")
    conceptos: Mapped[list["CfdiNominaConcepto"]] = relationship(
        back_populates="nomina", cascade="all, delete-orphan", lazy="selectin"
    )


class CfdiNominaConcepto(UUIDPKMixin, Base):
    """Cada percepción, deducción u otro pago del recibo. El reporte "solo
    conceptos" del despacho es exactamente esta tabla."""

    __tablename__ = "cfdi_nomina_conceptos"

    nomina_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cfdi_nominas.id", ondelete="CASCADE"), index=True, nullable=False)
    grupo: Mapped[str] = mapped_column(String(12), nullable=False)  # percepcion | deduccion | otro_pago
    tipo_codigo: Mapped[str | None] = mapped_column(String(5))
    clave: Mapped[str | None] = mapped_column(String(15))
    concepto: Mapped[str] = mapped_column(String(255), nullable=False)
    gravado: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    exento: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)

    nomina: Mapped[CfdiNomina] = relationship(back_populates="conceptos")
