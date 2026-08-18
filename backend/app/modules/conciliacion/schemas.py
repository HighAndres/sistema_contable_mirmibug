import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class CuentaCreate(BaseModel):
    banco: str = Field(min_length=1, max_length=60)
    alias: str = Field(min_length=1, max_length=60)
    numero: str | None = Field(default=None, max_length=30)
    moneda: str = Field(default="MXN", min_length=3, max_length=3)


class CuentaRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    banco: str
    alias: str
    numero: str | None
    moneda: str
    activo: bool


class MovimientoBancoRead(BaseModel):
    id: uuid.UUID
    cuenta_id: uuid.UUID
    cuenta_alias: str
    fecha: date
    concepto: str
    referencia: str | None
    cargo: float
    abono: float
    saldo: float | None
    estado: str
    conciliado_por: str | None
    nota: str | None
    cfdi_id: uuid.UUID | None
    cfdi_uuid: str | None
    cfdi_nombre: str | None
    cfdi_total: float | None
    archivo_nombre: str | None
    created_at: datetime


class MovimientosPageRead(BaseModel):
    items: list[MovimientoBancoRead]
    total: int


class ImportarBancoResponse(BaseModel):
    cuenta_id: uuid.UUID
    importados: int
    duplicados: int
    columnas_detectadas: dict[str, int]
    advertencias: list[str]
    fecha_min: date | None
    fecha_max: date | None


class ConciliarRequest(BaseModel):
    cfdi_id: uuid.UUID
    nota: str | None = Field(default=None, max_length=255)


class IgnorarRequest(BaseModel):
    nota: str | None = Field(default=None, max_length=255)


class AutoConciliarRequest(BaseModel):
    cuenta_id: uuid.UUID | None = None
    anio: int | None = Field(default=None, ge=2000, le=2100)
    mes: int | None = Field(default=None, ge=1, le=12)
    tolerancia_dias: int = Field(default=5, ge=0, le=60)


class AutoConciliarResponse(BaseModel):
    revisados: int
    conciliados: int
    sin_coincidencia: int
    ambiguos: int


class CandidatoCfdi(BaseModel):
    cfdi_id: uuid.UUID
    uuid_fiscal: str
    tipo: str
    direccion: str
    fecha: date
    nombre_contraparte: str
    rfc_contraparte: str
    total: float
    diferencia: float
    dias: int


class DeclaracionUpsert(BaseModel):
    ingresos_declarados: Decimal | None = None
    deducciones_declaradas: Decimal | None = None
    iva_declarado: Decimal | None = None
    isr_declarado: Decimal | None = None
    fecha_presentacion: date | None = None
    numero_operacion: str | None = Field(default=None, max_length=40)
    notas: str | None = Field(default=None, max_length=500)


class DeclaracionRead(BaseModel):
    anio: int
    mes: int
    ingresos_declarados: float | None
    deducciones_declaradas: float | None
    iva_declarado: float | None
    isr_declarado: float | None
    fecha_presentacion: date | None
    numero_operacion: str | None
    notas: str | None
    capturada: bool


class ColumnaSat(BaseModel):
    ingresos_cobrados: float  # PUE + REP emitidos (base sin IVA)
    egresos_pagados: float  # PUE + REP recibidos (base sin IVA)
    ingresos_facturados: float  # todo lo vigente (incluye PPD)
    iva_saldo: float
    isr_estimado: float
    num_cfdis: int


class ColumnaBanco(BaseModel):
    abonos: float
    cargos: float
    num_movimientos: int
    abonos_conciliados: float
    cargos_conciliados: float
    pendientes: int
    conciliados: int
    ignorados: int
    porcentaje_conciliado: float  # por número de movimientos


class Diferencias(BaseModel):
    ingresos_sat_vs_banco: float  # ingresos cobrados (SAT) − abonos conciliados+pendientes (banco)
    ingresos_sat_vs_declarado: float | None
    iva_sat_vs_declarado: float | None
    isr_sat_vs_declarado: float | None


class ResumenConciliacion(BaseModel):
    anio: int
    mes: int
    sat: ColumnaSat
    banco: ColumnaBanco
    declarado: DeclaracionRead
    diferencias: Diferencias
    semaforo: str  # ok | revisar | sin_declaracion
