import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.pedimentos.costeo import METODOS_PRORRATEO


class GastoAdicional(BaseModel):
    concepto: str = Field(min_length=1, max_length=80)
    # float (no Decimal) porque se guarda en una columna JSON; el motor lo
    # vuelve Decimal vía str() antes de operar (ver crud.total_gastos).
    monto: float = Field(ge=0)


# ---------- Partidas ----------


class PartidaCreate(BaseModel):
    """Captura manual de una partida (respaldo cuando no hay archivo M3)."""

    secuencia: int = Field(ge=1)
    fraccion: str = Field(min_length=1, max_length=10)
    nico: str | None = None
    descripcion: str = Field(min_length=1, max_length=255)
    pais_origen: str | None = None
    cantidad_umc: Decimal = Field(gt=0)
    umc_clave: str = Field(min_length=1, max_length=3)
    cantidad_umt: Decimal | None = None
    umt_clave: str | None = None
    precio_unitario: Decimal = Field(ge=0)
    valor_aduana: Decimal = Field(ge=0)
    valor_comercial: Decimal | None = None
    valor_usd: Decimal | None = None
    igi: Decimal = Field(default=Decimal("0"), ge=0)
    iva: Decimal = Field(default=Decimal("0"), ge=0)
    tasa_igi: Decimal | None = None
    tasa_iva: Decimal | None = None
    clave_prodserv: str | None = None
    clave_unidad_sat: str | None = None


class PartidaUpdate(BaseModel):
    """Lo que el usuario puede corregir sobre una partida ya importada."""

    descripcion: str | None = Field(default=None, min_length=1, max_length=255)
    clave_prodserv: str | None = None
    clave_unidad_sat: str | None = None
    producto_id: uuid.UUID | None = None


class PartidaCosteoRead(BaseModel):
    """Columnas calculadas (equivalentes a R..AJ del Excel)."""

    dta_asignado: float
    dta_pza: float
    igi_pza: float
    gastos_asignados: float
    gastos_pza: float
    utilidad_asignada: float
    utilidad_pza: float
    costo_unitario: float
    precio_unitario_venta: float
    subtotal: float
    iva_16: float
    total: float
    dif_iva: float


class PartidaRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    secuencia: int
    fraccion: str
    nico: str | None
    descripcion: str
    pais_origen: str | None
    cantidad_umc: float
    umc_clave: str
    umc_descripcion: str | None
    cantidad_umt: float | None
    umt_clave: str | None
    precio_unitario: float
    valor_aduana: float
    valor_comercial: float
    valor_usd: float
    igi: float
    iva: float
    tasa_igi: float | None
    tasa_iva: float | None
    clave_prodserv: str | None
    clave_unidad_sat: str | None
    producto_id: uuid.UUID | None
    producto_sku: str | None
    costeo: PartidaCosteoRead


# ---------- Pedimento ----------


class PedimentoCreate(BaseModel):
    """Captura manual (respaldo). Los datos mínimos son los del encabezado
    impreso + las partidas."""

    numero: str = Field(min_length=1, max_length=10)
    patente: str = Field(min_length=1, max_length=6)
    aduana: str = Field(min_length=1, max_length=5)
    clave_pedimento: str | None = None
    tipo_operacion: str | None = "1"
    rfc_importador: str | None = None
    referencia: str | None = None
    fecha_entrada: date | None = None
    fecha_pago: date | None = None
    tipo_cambio: Decimal = Field(gt=0)
    peso_bruto: Decimal | None = None
    incoterm: str | None = None
    proveedor_nombre: str | None = None
    proveedor_id_fiscal: str | None = None
    contenedores: list[str] | None = None
    dta: Decimal = Field(default=Decimal("0"), ge=0)
    otras_contribuciones: dict[str, str] | None = None
    gastos_adicionales: list[GastoAdicional] = []
    utilidad: Decimal = Field(default=Decimal("0"), ge=0)
    metodo_prorrateo: str = "partes_iguales"
    notas: str | None = None
    partidas: list[PartidaCreate] = Field(min_length=1)

    @field_validator("metodo_prorrateo")
    @classmethod
    def _metodo_valido(cls, v: str) -> str:
        if v not in METODOS_PRORRATEO:
            raise ValueError(f"metodo_prorrateo debe ser uno de {METODOS_PRORRATEO}")
        return v


class PedimentoUpdate(BaseModel):
    """Configuración del costeo y datos de control (solo en borrador)."""

    referencia: str | None = None
    notas: str | None = None
    dta: Decimal | None = Field(default=None, ge=0)
    gastos_adicionales: list[GastoAdicional] | None = None
    utilidad: Decimal | None = Field(default=None, ge=0)
    metodo_prorrateo: str | None = None

    @field_validator("metodo_prorrateo")
    @classmethod
    def _metodo_valido(cls, v: str | None) -> str | None:
        if v is not None and v not in METODOS_PRORRATEO:
            raise ValueError(f"metodo_prorrateo debe ser uno de {METODOS_PRORRATEO}")
        return v


class CosteoResumenRead(BaseModel):
    dta: float
    gastos_adicionales: float
    utilidad: float
    igi_total: float
    iva_importacion_total: float
    costo_total: float
    subtotal_venta: float
    iva_venta: float
    total_venta: float
    dif_iva_total: float


class PedimentoResumenRead(BaseModel):
    """Fila de la lista."""

    id: uuid.UUID
    numero_completo: str
    numero: str
    patente: str
    aduana: str
    clave_pedimento: str | None
    referencia: str | None
    fecha_pago: date | None
    tipo_cambio: float
    proveedor_nombre: str | None
    num_partidas: int
    valor_aduana_total: float
    dta: float
    igi_total: float
    iva_total: float
    estatus: str
    origen: str
    created_at: datetime


class PedimentoDetalleRead(PedimentoResumenRead):
    tipo_operacion: str | None
    rfc_importador: str | None
    fecha_entrada: date | None
    peso_bruto: float | None
    incoterm: str | None
    proveedor_id_fiscal: str | None
    contenedores: list[str] | None
    guias: list[str] | None
    otras_contribuciones: dict[str, str] | None
    gastos_adicionales: list[GastoAdicional]
    utilidad: float
    metodo_prorrateo: str
    aplicado_almacen_id: uuid.UUID | None
    archivo_nombre: str | None
    notas: str | None
    valor_usd_total: float
    resumen: CosteoResumenRead
    partidas: list[PartidaRead]


class ImportarM3Response(BaseModel):
    pedimento: PedimentoDetalleRead
    advertencias: list[str]


class AplicarInventarioRequest(BaseModel):
    codigo_almacen: str = Field(min_length=1)
    # Si una partida no tiene producto asignado, ¿crear el producto automáticamente?
    crear_productos_faltantes: bool = True
    categoria_nuevos: str | None = "Importación"


class AplicarInventarioResponse(BaseModel):
    pedimento_id: uuid.UUID
    movimientos_creados: int
    productos_creados: int
    costo_total: float
