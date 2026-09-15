import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class CfdiConceptoRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    descripcion: str
    cantidad: float
    unidad_codigo: str | None
    valor_unitario: float
    importe: float


class CfdiRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    uuid_fiscal: str
    version: str | None = None
    serie: str | None = None
    folio: str | None = None
    tipo: str
    direccion: str
    rfc_emisor: str
    nombre_emisor: str
    rfc_receptor: str
    nombre_receptor: str
    forma_pago_codigo: str | None
    metodo_pago_codigo: str | None = None
    uso_cfdi_codigo: str | None
    subtotal: float
    iva: float
    total: float
    fecha: date
    estatus: str
    tipo_comprobante: str | None = None
    origen: str = "mock"
    iva_retenido: float = 0
    isr_retenido: float = 0
    # Pago registrado a mano (solo facturas PPD).
    pago_manual_fecha: date | None = None
    pago_manual_nota: str | None = None
    # Derivados (no están en la tabla): estado de cobro/pago de la factura y
    # lo cubierto por REP. None en REP, nómina y notas de crédito.
    estado_pago: str | None = None  # pagada | parcial | pendiente
    pagado_rep: float = 0
    # Clasificación capturada por el contador.
    clasificacion: str | None = None  # deducible | no_deducible | deduccion_personal
    concepto: str | None = None
    cuenta_contable: str | None = None
    referencia_bancaria: str | None = None


CLASIFICACIONES = ("deducible", "no_deducible", "deduccion_personal")


class ClasificacionRequest(BaseModel):
    """Todos los campos son opcionales, pero se escriben tal cual llegan: mandar
    `null` en uno lo limpia. Es la captura del papel de trabajo del contador."""

    clasificacion: str | None = Field(default=None, pattern="^(deducible|no_deducible|deduccion_personal)$")
    concepto: str | None = Field(default=None, max_length=60)
    cuenta_contable: str | None = Field(default=None, max_length=20)
    referencia_bancaria: str | None = Field(default=None, max_length=40)


class ClasificacionMasivaRequest(ClasificacionRequest):
    """Misma clasificación aplicada a varios CFDIs de golpe: un ejercicio real
    trae ~1,500 gastos y se capturan por lotes (todos los peajes, todo lo de un
    proveedor…). Los campos que van en `null` NO se tocan, a diferencia de la
    edición de uno solo, para poder marcar solo el concepto sin borrar la cuenta."""

    cfdi_ids: list[uuid.UUID] = Field(min_length=1, max_length=500)


class ClasificacionMasivaResultado(BaseModel):
    actualizados: int
    omitidos: int  # no encontrados, de otra empresa o no clasificables (REP/nómina)


class ReporteCfdi(BaseModel):
    """Reporte tabular listo para exportar, con el layout de los despachos."""

    formato: str
    descripcion: str
    columnas: list[str]
    filas: list[list]
    total: int  # CFDIs que cumplen los filtros (puede ser mayor que len(filas))
    truncado: bool
    #: Columnas que hoy siempre salen vacías porque aún no guardamos ese dato.
    sin_dato: list[str]


class ValoresClasificacion(BaseModel):
    """Lo ya usado en la empresa, para autocompletar sin inventar un catálogo."""

    conceptos: list[str]
    cuentas_contables: list[str]
    sin_clasificar: int


class PagoManualRequest(BaseModel):
    fecha: date
    nota: str | None = Field(default=None, max_length=255)


class PagoDoctoRead(BaseModel):
    cfdi_pago_id: uuid.UUID
    uuid_pago: str
    uuid_relacionado: str
    num_parcialidad: int | None
    imp_saldo_anterior: float | None
    imp_pagado: float
    imp_saldo_insoluto: float | None
    iva_pagado: float
    fecha_pago: date | None
    forma_pago_codigo: str | None


class CfdiDetalleRead(CfdiRead):
    conceptos: list[CfdiConceptoRead]
    alertas: list["CfdiAlertaRead"] = []
    # Si es factura PPD: complementos de pago que la pagan y saldo pendiente.
    pagos_recibidos: list[PagoDoctoRead] = []
    saldo_pendiente: float | None = None
    # Si es REP: documentos que paga.
    pagos_relacionados: list[PagoDoctoRead] = []
    tiene_xml: bool = False


class CfdiPage(BaseModel):
    items: list[CfdiRead]
    total: int
    limit: int
    offset: int


class ResumenTipo(BaseModel):
    cantidad: int
    cancelados: int
    ppd: int
    subtotal: float
    iva: float
    total: float


class CfdiResumen(BaseModel):
    """Totales por tipo de comprobante para los filtros activos (tarjetas de la lista)."""

    ingreso: ResumenTipo
    egreso: ResumenTipo
    pago: ResumenTipo
    nomina: ResumenTipo
    nota_credito: ResumenTipo
    anios: list[int]


class CfdiAlertaRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    regla_codigo: str
    severidad: str
    detalle: str
    created_at: datetime
