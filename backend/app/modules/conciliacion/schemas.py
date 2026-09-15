import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ESTADOS_MOVIMIENTO = ("pendiente", "parcial", "conciliado", "ignorado")


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


class LigaRead(BaseModel):
    """Un CFDI ligado al movimiento y con cuánto."""

    cfdi_id: uuid.UUID
    uuid_fiscal: str
    tipo: str
    serie_folio: str | None
    fecha: date
    nombre_contraparte: str
    rfc_contraparte: str
    total: float
    importe: float


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
    estado: str  # pendiente | parcial | conciliado | ignorado
    conciliado_por: str | None
    nota: str | None
    ligas: list[LigaRead]
    importe_ligado: float
    restante: float
    # Resumen para la tabla: contraparte del primer CFDI ligado (o "N CFDI").
    cfdi_uuid: str | None
    cfdi_nombre: str | None
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


class LigaInput(BaseModel):
    cfdi_id: uuid.UUID
    # Sin importe: se aplica lo que quepa (mínimo entre el saldo del CFDI y lo que
    # le falta al movimiento).
    importe: Decimal | None = Field(default=None, gt=0)


class ConciliarRequest(BaseModel):
    """`cfdi_id` (1:1, forma corta) o `ligas` (uno o varios CFDI con importe)."""

    cfdi_id: uuid.UUID | None = None
    ligas: list[LigaInput] = Field(default_factory=list, max_length=50)
    nota: str | None = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def _al_menos_uno(self):
        if self.cfdi_id is None and not self.ligas:
            raise ValueError("Indica cfdi_id o al menos una liga")
        if self.cfdi_id is not None and not any(l.cfdi_id == self.cfdi_id for l in self.ligas):
            self.ligas = [LigaInput(cfdi_id=self.cfdi_id), *self.ligas]
        vistos = set()
        for l in self.ligas:
            if l.cfdi_id in vistos:
                raise ValueError("Hay un CFDI repetido en las ligas")
            vistos.add(l.cfdi_id)
        return self


class IgnorarRequest(BaseModel):
    nota: str | None = Field(default=None, max_length=255)


class AutoConciliarRequest(BaseModel):
    cuenta_id: uuid.UUID | None = None
    anio: int | None = Field(default=None, ge=2000, le=2100)
    mes: int | None = Field(default=None, ge=1, le=12)
    tolerancia_dias: int = Field(default=5, ge=0, le=365)


class AutoConciliarResponse(BaseModel):
    revisados: int
    conciliados: int
    sin_coincidencia: int
    ambiguos: int  # varios CFDI con el monto exacto: el usuario elige
    con_sugerencias: int  # sin match exacto pero con candidatos similares/parciales o combinaciones


class CandidatoCfdi(BaseModel):
    cfdi_id: uuid.UUID
    uuid_fiscal: str
    tipo: str
    direccion: str
    metodo_pago: str | None
    serie_folio: str | None
    fecha: date
    nombre_contraparte: str
    rfc_contraparte: str
    total: float
    pagado_rep: float  # ya cubierto por complementos de pago (facturas PPD)
    ligado_otros: float  # ya aplicado desde otros movimientos bancarios
    saldo: float  # total − pagado_rep − ligado_otros: lo que aún se puede ligar
    diferencia: float  # saldo − restante del movimiento
    dias: int  # |fecha movimiento − fecha CFDI|
    pagado_despues: bool  # el movimiento es posterior al CFDI (lo normal)
    # exacto: saldo == restante · similar: dentro de la tolerancia (comisión/redondeo)
    # parcial: el CFDI es mayor → el movimiento lo paga en parte (N:1)
    # menor: el CFDI es menor → se puede combinar con otros (1:N)
    coincidencia: str
    contraparte_en_concepto: bool  # el nombre/RFC aparece en el concepto del banco
    importe_sugerido: float  # lo que se aplicaría al ligarlo solo


class Combinacion(BaseModel):
    """Varios CFDI de la misma contraparte que juntos suman el movimiento (1:N)."""

    cfdi_ids: list[uuid.UUID]
    rfc_contraparte: str
    nombre_contraparte: str
    total: float
    diferencia: float


class MovimientoResumen(BaseModel):
    id: uuid.UUID
    fecha: date
    monto: float
    importe_ligado: float
    restante: float


class CandidatosResponse(BaseModel):
    movimiento: MovimientoResumen
    candidatos: list[CandidatoCfdi]
    combinaciones: list[Combinacion]


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
    parciales: int
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
