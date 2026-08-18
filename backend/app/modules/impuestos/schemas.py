from decimal import Decimal

from pydantic import BaseModel, Field, field_validator


class DesgloseIvaRead(BaseModel):
    concepto: str
    num_cfdis: int
    base: float
    iva: float


class IvaRead(BaseModel):
    anio: int
    mes: int | None
    trasladado_cobrado: float
    acreditable_pagado: float
    saldo: float  # > 0 a cargo, < 0 a favor
    trasladado_ppd_pendiente: float
    acreditable_ppd_pendiente: float
    emitidas: list[DesgloseIvaRead]
    recibidas: list[DesgloseIvaRead]
    anios_disponibles: list[int]


class MesIsrRead(BaseModel):
    mes: int
    ingresos_mes: float
    deducciones_mes: float
    ingresos_acumulados: float
    deducciones_acumuladas: float
    base: float
    tasa_aplicada: float | None
    isr_acumulado: float
    pagos_anteriores: float
    isr_del_mes: float


class IsrRead(BaseModel):
    anio: int
    hasta_mes: int
    mecanica: str
    descripcion: str
    tipo_persona: str
    regimen_fiscal_codigo: str | None
    coeficiente_utilidad: float | None
    meses: list[MesIsrRead]
    advertencias: list[str]
    anios_disponibles: list[int]


class ConfiguracionFiscalRead(BaseModel):
    rfc: str
    razon_social: str
    tipo_persona: str
    regimen_fiscal_codigo: str | None
    coeficiente_utilidad: float | None
    mecanica_isr: str


class ConfiguracionFiscalUpdate(BaseModel):
    regimen_fiscal_codigo: str | None = Field(default=None, max_length=10)
    coeficiente_utilidad: Decimal | None = Field(default=None, ge=0, le=1)

    @field_validator("coeficiente_utilidad")
    @classmethod
    def _cuatro_decimales(cls, v: Decimal | None) -> Decimal | None:
        return v.quantize(Decimal("0.0001")) if v is not None else None
