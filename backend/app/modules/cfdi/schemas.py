import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class CfdiConceptoRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    descripcion: str
    cantidad: float
    unidad_codigo: str | None
    clave_prodserv: str | None = None
    valor_unitario: float
    importe: float


class TasaIvaRead(BaseModel):
    """Una tasa de IVA trasladado del comprobante: "16%", "8%", "0%" o "Exento"."""

    etiqueta: str
    base: float
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
    # Derivados contra la conciliación bancaria: cuánto del CFDI está ligado a
    # movimientos del estado de cuenta. None/0 = sin conciliar.
    conciliado: str | None = None  # conciliado | parcial
    conciliado_importe: float = 0
    # Derivado: si el comprobante cuenta para la declaración del periodo. Se
    # calcula solo (vigente + deducible + pagada o conciliada) y el contador lo
    # mueve a mano con la clasificación. None en REP y nómina.
    en_declaracion: bool | None = None
    # Desglose del IVA trasladado por tasa (de cfdi_impuestos). Vacío en los
    # CFDI simulados o cargados antes de guardarse el desglose.
    desglose_iva: list[TasaIvaRead] = []
    # Si es REP (tipo pago): fecha e importes del complemento, para no mostrar
    # subtotal/total que en un REP siempre valen 0.
    rep_fecha_pago: date | None = None
    rep_importe_pagado: float = 0
    rep_iva_pagado: float = 0
    # Si es recibo de nómina: lo que pide el listado (desglose y filtros).
    nomina_fecha_pago: date | None = None
    nomina_percepciones: float | None = None
    nomina_deducciones: float | None = None
    nomina_otros_pagos: float | None = None
    registro_patronal: str | None = None
    entidad_codigo: str | None = None
    periodicidad_codigo: str | None = None


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


class ValoresFiltros(BaseModel):
    """Valores presentes en los CFDI de la empresa, para poblar los filtros de
    la lista (uso de CFDI y los de nómina) sin inventar catálogos."""

    usos_cfdi: list[str]
    registros_patronales: list[str]
    entidades: list[str]
    periodicidades: list[str]


class PagoManualRequest(BaseModel):
    fecha: date
    nota: str | None = Field(default=None, max_length=255)


class PagoDoctoRead(BaseModel):
    cfdi_pago_id: uuid.UUID
    uuid_pago: str
    uuid_relacionado: str
    # Id de la factura PPD que liquida, si está en la bóveda (para ir directo).
    cfdi_relacionado_id: uuid.UUID | None = None
    num_parcialidad: int | None
    imp_saldo_anterior: float | None
    imp_pagado: float
    imp_saldo_insoluto: float | None
    iva_pagado: float
    fecha_pago: date | None
    forma_pago_codigo: str | None


class DesgloseImpuestoRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    naturaleza: str  # traslado | retencion | no_objeto
    impuesto: str  # 001 ISR · 002 IVA · 003 IEPS · local
    tipo_factor: str | None
    tasa: float | None
    base: float
    importe: float
    nombre_local: str | None


class LigaBancariaRead(BaseModel):
    """Movimiento del estado de cuenta ligado a este CFDI en la conciliación."""

    movimiento_id: uuid.UUID
    fecha: date
    concepto: str
    referencia: str | None
    cuenta: str  # alias de la cuenta bancaria
    importe: float  # lo aplicado a este CFDI


class NominaConceptoRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    grupo: str  # percepcion | deduccion | otro_pago
    tipo_codigo: str | None
    clave: str | None
    concepto: str
    gravado: float
    exento: float


class NominaDetalleRead(BaseModel):
    """Complemento de nómina del recibo. Los datos personales del trabajador
    (CURP, NSS, cuenta bancaria, salarios de cotización) solo se llenan si el
    usuario tiene el permiso nomina.leer."""

    tipo_nomina: str | None
    fecha_pago: date | None
    fecha_inicial_pago: date | None
    fecha_final_pago: date | None
    num_dias_pagados: float | None
    total_percepciones: float
    total_deducciones: float
    total_otros_pagos: float
    registro_patronal: str | None
    periodicidad_pago: str | None
    clave_ent_fed: str | None
    num_empleado: str | None
    departamento: str | None
    puesto: str | None
    # Solo con nomina.leer:
    curp_receptor: str | None = None
    num_seguridad_social: str | None = None
    banco: str | None = None
    cuenta_bancaria: str | None = None
    salario_base_cot_apor: float | None = None
    salario_diario_integrado: float | None = None
    conceptos: list[NominaConceptoRead] = []


class CfdiDetalleRead(CfdiRead):
    conceptos: list[CfdiConceptoRead]
    alertas: list["CfdiAlertaRead"] = []
    # Si es factura PPD: complementos de pago que la pagan y saldo pendiente.
    pagos_recibidos: list[PagoDoctoRead] = []
    saldo_pendiente: float | None = None
    # Si es REP: documentos que paga.
    pagos_relacionados: list[PagoDoctoRead] = []
    tiene_xml: bool = False
    # Desglose completo de impuestos por tasa (traslados, retenciones, locales).
    impuestos: list[DesgloseImpuestoRead] = []
    # Movimientos bancarios ligados en la conciliación.
    ligas_bancarias: list[LigaBancariaRead] = []
    # Complemento de nómina (solo recibos de nómina).
    nomina: NominaDetalleRead | None = None


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
