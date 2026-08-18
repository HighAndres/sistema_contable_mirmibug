import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


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
