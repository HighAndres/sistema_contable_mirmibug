import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

TIPOS = ("cliente", "proveedor", "ambos")


class TerceroBase(BaseModel):
    nombre: str = Field(min_length=1, max_length=255)
    tipo: str = "cliente"
    regimen_fiscal_codigo: str | None = Field(default=None, max_length=10)
    codigo_postal: str | None = Field(default=None, max_length=5)
    uso_cfdi_default: str | None = Field(default=None, max_length=5)
    email: EmailStr | None = None
    telefono: str | None = Field(default=None, max_length=30)
    contacto: str | None = Field(default=None, max_length=120)
    dias_credito: int = Field(default=0, ge=0, le=365)
    limite_credito: Decimal | None = Field(default=None, ge=0)
    notas: str | None = Field(default=None, max_length=500)
    activo: bool = True

    @field_validator("tipo")
    @classmethod
    def _tipo(cls, v: str) -> str:
        if v not in TIPOS:
            raise ValueError(f"tipo debe ser uno de {TIPOS}")
        return v


class TerceroCreate(TerceroBase):
    rfc: str = Field(min_length=12, max_length=13)

    @field_validator("rfc")
    @classmethod
    def _rfc(cls, v: str) -> str:
        v = v.strip().upper()
        if not v.replace("&", "").replace("Ñ", "N").isalnum():
            raise ValueError("RFC inválido")
        return v


class TerceroUpdate(BaseModel):
    nombre: str | None = Field(default=None, min_length=1, max_length=255)
    tipo: str | None = None
    regimen_fiscal_codigo: str | None = None
    codigo_postal: str | None = None
    uso_cfdi_default: str | None = None
    email: EmailStr | None = None
    telefono: str | None = None
    contacto: str | None = None
    dias_credito: int | None = Field(default=None, ge=0, le=365)
    limite_credito: Decimal | None = Field(default=None, ge=0)
    notas: str | None = None
    activo: bool | None = None

    @field_validator("tipo")
    @classmethod
    def _tipo(cls, v: str | None) -> str | None:
        if v is not None and v not in TIPOS:
            raise ValueError(f"tipo debe ser uno de {TIPOS}")
        return v


class Antiguedad(BaseModel):
    """Saldo pendiente por antigüedad (días desde la fecha del CFDI)."""

    d0_30: float
    d31_60: float
    d61_90: float
    d90_mas: float
    total: float
    num_cfdis: int


class TerceroRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    rfc: str
    nombre: str
    tipo: str
    regimen_fiscal_codigo: str | None
    codigo_postal: str | None
    uso_cfdi_default: str | None
    email: str | None
    telefono: str | None
    contacto: str | None
    dias_credito: int
    limite_credito: float | None
    notas: str | None
    origen: str
    activo: bool
    es_efos: bool = False
    created_at: datetime


class TerceroResumenRead(TerceroRead):
    """Fila de la lista con lo que se calcula de la bóveda."""

    num_cfdis: int = 0
    facturado_12m: float = 0  # últimos 12 meses (vigentes)
    saldo_pendiente: float = 0  # PPD sin pagar (por cobrar si cliente / por pagar si proveedor)
    ultimo_cfdi: date | None = None


class TerceroDetalleRead(TerceroResumenRead):
    por_cobrar: Antiguedad
    por_pagar: Antiguedad
    total_emitido: float  # histórico
    total_recibido: float


class SincronizarResponse(BaseModel):
    creados: int
    actualizados: int
    total: int


class CargaTercerosResponse(BaseModel):
    creados: int
    actualizados: int
    errores: list[dict]
