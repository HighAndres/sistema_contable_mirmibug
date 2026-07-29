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
    tipo: str
    direccion: str
    rfc_emisor: str
    nombre_emisor: str
    rfc_receptor: str
    nombre_receptor: str
    forma_pago_codigo: str | None
    uso_cfdi_codigo: str | None
    subtotal: float
    iva: float
    total: float
    fecha: date
    estatus: str


class CfdiDetalleRead(CfdiRead):
    conceptos: list[CfdiConceptoRead]
    alertas: list["CfdiAlertaRead"] = []


class CfdiPage(BaseModel):
    items: list[CfdiRead]
    total: int
    limit: int
    offset: int


class CfdiAlertaRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    regla_codigo: str
    severidad: str
    detalle: str
    created_at: datetime
