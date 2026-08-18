import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AlmacenRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    nombre: str
    codigo: str
    activo: bool


class AlmacenCreate(BaseModel):
    nombre: str
    codigo: str


class ProductoRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    sku: str
    nombre: str
    tipo: str
    categoria: str | None
    unidad_codigo: str | None
    costo_unitario: float
    atributos: dict | None
    clave_prodserv: str | None = None
    activo: bool


class ProductoCreate(BaseModel):
    sku: str
    nombre: str
    tipo: str = "producto"
    categoria: str | None = None
    unidad_codigo: str | None = None
    costo_unitario: float = 0
    atributos: dict | None = None


class StockItem(BaseModel):
    producto_id: uuid.UUID
    sku: str
    nombre_producto: str
    categoria: str | None
    almacen_id: uuid.UUID
    codigo_almacen: str
    disponible: int


class MovimientoCreate(BaseModel):
    sku: str
    codigo_almacen: str
    tipo: str  # entrada | salida | ajuste
    cantidad: int
    referencia: str | None = None
    nota: str | None = None


class MovimientoRead(BaseModel):
    id: uuid.UUID
    tipo: str
    cantidad: int
    referencia: str | None
    nota: str | None
    costo_unitario: float | None
    fecha: datetime
    sku: str
    nombre_producto: str
    codigo_almacen: str

    @classmethod
    def from_orm_model(cls, m) -> "MovimientoRead":
        return cls(
            id=m.id,
            tipo=m.tipo,
            cantidad=m.cantidad,
            costo_unitario=float(m.costo_unitario) if m.costo_unitario is not None else None,
            referencia=m.referencia,
            nota=m.nota,
            fecha=m.fecha,
            sku=m.producto.sku,
            nombre_producto=m.producto.nombre,
            codigo_almacen=m.almacen.codigo,
        )
