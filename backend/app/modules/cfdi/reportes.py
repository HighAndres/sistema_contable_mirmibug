"""Reportes de CFDI con el mismo layout que usan los despachos.

Jacob trabaja hoy bajando el reporte de un portal (ONEFACTURE o MiAdminPro),
pegándolo en su archivo de impuestos y escribiendo encima las columnas manuales.
El reporte "GENERAL" de ONEFACTURE es, columna por columna, la hoja
INGRESOS/GASTOS de esos papeles de trabajo, así que aquí se reproduce tal cual y
se le añaden al final las columnas que él captura a mano y que nosotros ya
guardamos (clasificación, concepto, cuenta contable, referencia y fecha de pago).

Columnas que el SAT sí publica pero que hoy NO tenemos de dónde sacar salen
vacías: se listan en `sin_dato` para que quede claro en la UI y no parezca que el
dato se perdió. Se irán llenando conforme el parser guarde más del XML.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal

from app.modules.cfdi.models import Cfdi

MESES = ["", "ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO", "JULIO", "AGOSTO", "SEPTIEMBRE", "OCTUBRE", "NOVIEMBRE", "DICIEMBRE"]

TIPO_SAT = {"I": "I - Ingreso", "E": "E - Egreso", "P": "P - Pago", "N": "N - Nómina", "T": "T - Traslado"}
ESTADO_SAT = {"vigente": "VIGENTE", "cancelado": "CANCELADO", "en_proceso": "EN PROCESO DE CANCELACIÓN"}
CLASIFICACION_SAT = {
    "deducible": "DEDUCIBLE",
    "no_deducible": "NO DEDUCIBLE",
    "deduccion_personal": "DEDUCCION PERSONAL",
}


@dataclass
class Columna:
    titulo: str
    valor: Callable[["FilaCfdi"], object]
    #: True cuando hoy siempre sale vacía (no tenemos el dato todavía).
    sin_dato: bool = False


@dataclass
class FilaCfdi:
    """Un CFDI con lo que hace falta calcular fuera de la fila."""

    cfdi: Cfdi
    #: Fecha en que se cobró/pagó (REP, pago manual o la propia fecha si es PUE).
    fecha_pago: object = None
    #: UUID del REP que la liquidó, si lo hay.
    uuid_pago: str | None = None
    pagado: Decimal = Decimal("0")


def _fecha(v) -> str:
    return v.isoformat() if v is not None else ""


def _conceptos(f: FilaCfdi) -> str:
    return " | ".join(c.descripcion for c in f.cfdi.conceptos)


def _claves(f: FilaCfdi) -> str:
    return " | ".join(c.clave_prodserv for c in f.cfdi.conceptos if c.clave_prodserv)


def _imp(f: FilaCfdi, naturaleza: str, impuesto: str, tasa=None, factor: str | None = None) -> tuple[float, float]:
    """(base, importe) de un impuesto a una tasa concreta. Si `tasa` es None se
    suman todas las del impuesto."""
    base = importe = Decimal("0")
    for i in f.cfdi.impuestos:
        if i.naturaleza != naturaleza or i.impuesto != impuesto or i.nombre_local:
            continue
        if factor is not None and (i.tipo_factor or "") != factor:
            continue
        if tasa is not None and (i.tasa is None or Decimal(i.tasa) != Decimal(str(tasa))):
            continue
        base += Decimal(i.base)
        importe += Decimal(i.importe)
    return float(base), float(importe)


def _base(f: FilaCfdi, naturaleza: str, impuesto: str, tasa=None, factor: str | None = None) -> float:
    return _imp(f, naturaleza, impuesto, tasa, factor)[0]


def _importe(f: FilaCfdi, naturaleza: str, impuesto: str, tasa=None, factor: str | None = None) -> float:
    return _imp(f, naturaleza, impuesto, tasa, factor)[1]


def _local(f: FilaCfdi, naturaleza: str) -> float:
    return float(sum((Decimal(i.importe) for i in f.cfdi.impuestos if i.nombre_local and i.naturaleza == naturaleza), Decimal("0")))


def _no_objeto(f: FilaCfdi) -> float:
    return float(sum((Decimal(i.base) for i in f.cfdi.impuestos if i.naturaleza == "no_objeto"), Decimal("0")))


def _estado_pago(f: FilaCfdi) -> str:
    c = f.cfdi
    if c.tipo not in ("ingreso", "egreso"):
        return ""
    cobro = c.direccion == "emitido"
    if c.metodo_pago_codigo != "PPD":
        return "COBRADO" if cobro else "PAGADO"
    if f.fecha_pago is None:
        return "PENDIENTE"
    return "COBRADO" if cobro else "PAGADO"


# Layout del reporte GENERAL de ONEFACTURE (= hoja INGRESOS/GASTOS del papel de
# trabajo). El orden importa: el contador pega esto directo en su archivo.
COLUMNAS_GENERAL: list[Columna] = [
    Columna("Periodo", lambda f: f.cfdi.fecha.month),
    Columna("Version", lambda f: f.cfdi.version or ""),
    Columna("UUID", lambda f: f.cfdi.uuid_fiscal),
    Columna("UUIDs relacionados", lambda f: " | ".join(r.uuid_relacionado for r in f.cfdi.relacionados)),
    Columna("Tipo relacion", lambda f: " | ".join(sorted({r.tipo_relacion for r in f.cfdi.relacionados if r.tipo_relacion}))),
    Columna("CP Expedicion", lambda f: f.cfdi.lugar_expedicion or ""),
    Columna("Serie", lambda f: f.cfdi.serie or ""),
    Columna("Folio", lambda f: f.cfdi.folio or ""),
    Columna("Tipo", lambda f: TIPO_SAT.get(f.cfdi.tipo_comprobante or "", "")),
    Columna("Fecha emision", lambda f: _fecha(f.cfdi.fecha)),
    Columna("Fecha certificacion", lambda f: _fecha(f.cfdi.fecha_timbrado)),
    Columna("pacCertifico", lambda f: f.cfdi.pac_rfc or ""),
    Columna("Regimen emisor", lambda f: f.cfdi.regimen_emisor or ""),
    Columna("RFC emisor", lambda f: f.cfdi.rfc_emisor),
    Columna("Razon emisor", lambda f: f.cfdi.nombre_emisor),
    Columna("RFC receptor", lambda f: f.cfdi.rfc_receptor),
    Columna("Razon receptor", lambda f: f.cfdi.nombre_receptor),
    Columna("Regimen receptor", lambda f: f.cfdi.regimen_receptor or ""),
    Columna("Domicilio receptor", lambda f: f.cfdi.domicilio_receptor or ""),
    Columna("Claves de productos", _claves),
    Columna("Conceptos", _conceptos),
    Columna("Cuenta Predial", lambda f: f.cfdi.cuenta_predial or ""),
    Columna("Uso CFDI", lambda f: f.cfdi.uso_cfdi_codigo or ""),
    Columna("Complementos", lambda f: f.cfdi.complementos or ""),
    Columna("Global periodicidad", lambda f: f.cfdi.global_periodicidad or ""),
    Columna("Global meses", lambda f: f.cfdi.global_meses or ""),
    Columna("Global año", lambda f: f.cfdi.global_anio or ""),
    Columna("Condiciones de pago", lambda f: f.cfdi.condiciones_pago or ""),
    Columna("Efecto", lambda f: "", sin_dato=True),
    Columna("Estado", lambda f: ESTADO_SAT.get(f.cfdi.estatus, "")),
    Columna("Fecha proceso cancelacion", lambda f: _fecha(f.cfdi.fecha_cancelacion)),
    Columna("Estado cancelacion", lambda f: "CANCELADO" if f.cfdi.estatus == "cancelado" else ("EN PROCESO" if f.cfdi.estatus == "en_proceso" else "")),
    Columna("Estado proceso cancelacion", lambda f: "EN PROCESO" if f.cfdi.estatus == "en_proceso" else ""),
    Columna("Motivo cancelacion", lambda f: f.cfdi.motivo_cancelacion or ""),
    Columna("Folio sustitucion cancelacion", lambda f: f.cfdi.folio_sustitucion or ""),
    Columna("Moneda", lambda f: f.cfdi.moneda or "MXN"),
    Columna("Tipo de cambio", lambda f: float(f.cfdi.tipo_cambio) if f.cfdi.tipo_cambio is not None else ""),
    Columna("Exportacion", lambda f: f.cfdi.exportacion or ""),
    Columna("Metodo pago", lambda f: f.cfdi.metodo_pago_codigo or ""),
    Columna("Forma pago", lambda f: f.cfdi.forma_pago_codigo or ""),
    Columna("SubTotalCombustibles", lambda f: "", sin_dato=True),
    Columna("SubTotal", lambda f: float(f.cfdi.subtotal)),
    Columna("Descuento", lambda f: float(f.cfdi.descuento or 0)),
    Columna("IVA Trasladado 16%", lambda f: float(f.cfdi.iva)),
    Columna("IVA Exento", lambda f: _base(f, "traslado", "002", factor="Exento")),
    Columna("No Objeto", _no_objeto),
    Columna("IVA Retenido", lambda f: float(f.cfdi.iva_retenido)),
    Columna("ISR Retenido", lambda f: float(f.cfdi.isr_retenido)),
    Columna("IEPS Trasladado No Desglosado", lambda f: "", sin_dato=True),
    Columna("IEPS Trasladado", lambda f: _importe(f, "traslado", "003")),
    Columna("IEPS Retenido", lambda f: _importe(f, "retencion", "003")),
    Columna("Local retenido", lambda f: _local(f, "retencion")),
    Columna("Local trasladado", lambda f: _local(f, "traslado")),
    Columna("TotalCombustibles", lambda f: "", sin_dato=True),
    Columna("Total", lambda f: float(f.cfdi.total)),
]

# Lo que el contador escribe a mano en su papel de trabajo y nosotros ya
# guardamos: por eso el reporte le llega resuelto y no en blanco.
COLUMNAS_TRABAJO: list[Columna] = [
    Columna("TIPO DE DEDUCCION", lambda f: CLASIFICACION_SAT.get(f.cfdi.clasificacion or "", "")),
    Columna("CONCEPTO", lambda f: f.cfdi.concepto or ""),
    Columna("CUENTA CONTABLE", lambda f: f.cfdi.cuenta_contable or ""),
    Columna("PAG/PEN", _estado_pago),
    Columna("REF BANCARIA", lambda f: f.cfdi.referencia_bancaria or ""),
    Columna("COMPLEMENTO PAGO", lambda f: f.uuid_pago or ""),
    Columna("FECHA PAGO", lambda f: _fecha(f.fecha_pago)),
    Columna("MES PAGO", lambda f: f.fecha_pago.month if f.fecha_pago is not None else ""),
]

# Complementos de pago: una fila por documento liquidado, que es como los
# revisa el contador (a qué factura se aplicó cada parcialidad).
COLUMNAS_PAGOS: list[Columna] = [
    Columna("Periodo", lambda f: f.cfdi.fecha.month),
    Columna("UUID", lambda f: f.cfdi.uuid_fiscal),
    Columna("Serie", lambda f: f.cfdi.serie or ""),
    Columna("Folio", lambda f: f.cfdi.folio or ""),
    Columna("Fecha emision", lambda f: _fecha(f.cfdi.fecha)),
    Columna("RFC emisor", lambda f: f.cfdi.rfc_emisor),
    Columna("Razon emisor", lambda f: f.cfdi.nombre_emisor),
    Columna("RFC receptor", lambda f: f.cfdi.rfc_receptor),
    Columna("Razon receptor", lambda f: f.cfdi.nombre_receptor),
    Columna("Estado", lambda f: ESTADO_SAT.get(f.cfdi.estatus, "")),
    Columna("Moneda", lambda f: f.cfdi.moneda or "MXN"),
]

# Datos del documento relacionado dentro del REP (se llenan por fila expandida).
COLUMNAS_DOCTO: list[Columna] = [
    Columna("UUID documento", lambda f: getattr(f, "_docto").uuid_relacionado),
    Columna("Serie documento", lambda f: getattr(f, "_docto").serie or ""),
    Columna("Folio documento", lambda f: getattr(f, "_docto").folio or ""),
    Columna("Num parcialidad", lambda f: getattr(f, "_docto").num_parcialidad or ""),
    Columna("Saldo anterior", lambda f: float(getattr(f, "_docto").imp_saldo_anterior or 0)),
    Columna("Importe pagado", lambda f: float(getattr(f, "_docto").imp_pagado)),
    Columna("Saldo insoluto", lambda f: float(getattr(f, "_docto").imp_saldo_insoluto or 0)),
    Columna("IVA del pago", lambda f: float(getattr(f, "_docto").iva_pagado)),
    Columna("Fecha pago", lambda f: _fecha(getattr(f, "_docto").fecha_pago)),
    Columna("Forma pago", lambda f: getattr(f, "_docto").forma_pago_codigo or ""),
]


# Columnas de impuestos del general que el formato "comp" sustituye por el
# desglose tasa por tasa.
COLUMNAS_IMPUESTOS_GENERAL = {
    "IVA Trasladado 16%",
    "IVA Exento",
    "No Objeto",
    "IVA Retenido",
    "ISR Retenido",
    "IEPS Trasladado No Desglosado",
    "IEPS Trasladado",
    "IEPS Retenido",
    "Local retenido",
    "Local trasladado",
}

# --- "Facturas Comp" de MiAdminPro: el mismo CFDI pero con base e importe de
# cada tasa por separado, que es lo que el contador cuadra contra la declaración.
TASAS_IVA = [("16", Decimal("0.16")), ("8", Decimal("0.08")), ("0", Decimal("0"))]
TASAS_IEPS = [("3", Decimal("0.03")), ("6", Decimal("0.06")), ("8", Decimal("0.08")), ("26.5", Decimal("0.265")), ("30", Decimal("0.30")), ("53", Decimal("0.53"))]


def _cols_tasas() -> list[Columna]:
    cols: list[Columna] = []
    for etiqueta, tasa in TASAS_IVA:
        cols.append(Columna(f"IVA {etiqueta} Base", lambda f, t=tasa: _base(f, "traslado", "002", t, factor="Tasa")))
        cols.append(Columna(f"IVA {etiqueta} Importe", lambda f, t=tasa: _importe(f, "traslado", "002", t, factor="Tasa")))
    cols.append(Columna("IVA Exento Base", lambda f: _base(f, "traslado", "002", factor="Exento")))
    cols.append(Columna("No Objeto Base", _no_objeto))
    for etiqueta, tasa in TASAS_IEPS:
        cols.append(Columna(f"IEPS {etiqueta} Base", lambda f, t=tasa: _base(f, "traslado", "003", t)))
        cols.append(Columna(f"IEPS {etiqueta} Importe", lambda f, t=tasa: _importe(f, "traslado", "003", t)))
    cols.append(Columna("Ret IVA Importe", lambda f: _importe(f, "retencion", "002")))
    cols.append(Columna("Ret ISR Importe", lambda f: _importe(f, "retencion", "001")))
    cols.append(Columna("Ret IEPS Importe", lambda f: _importe(f, "retencion", "003")))
    cols.append(Columna("Local trasladado", lambda f: _local(f, "traslado")))
    cols.append(Columna("Local retenido", lambda f: _local(f, "retencion")))
    return cols


# --- Nómina: un recibo por fila, como el reporte de nóminas del despacho.
def _nom(campo: str, formato=None):
    def valor(f: FilaCfdi):
        n = f.cfdi.nomina
        if n is None:
            return ""
        v = getattr(n, campo, None)
        if v is None:
            return ""
        return formato(v) if formato else v

    return valor


COLUMNAS_NOMINA: list[Columna] = [
    Columna("Periodo", lambda f: f.cfdi.fecha.month),
    Columna("UUID", lambda f: f.cfdi.uuid_fiscal),
    Columna("Serie", lambda f: f.cfdi.serie or ""),
    Columna("Folio", lambda f: f.cfdi.folio or ""),
    Columna("Fecha emision", lambda f: _fecha(f.cfdi.fecha)),
    Columna("Estado", lambda f: ESTADO_SAT.get(f.cfdi.estatus, "")),
    Columna("RFC Emisor", lambda f: f.cfdi.rfc_emisor),
    Columna("Nombre Emisor", lambda f: f.cfdi.nombre_emisor),
    Columna("RegistroPatronal", _nom("registro_patronal")),
    Columna("RFC Receptor", lambda f: f.cfdi.rfc_receptor),
    Columna("Nombre Receptor", lambda f: f.cfdi.nombre_receptor),
    Columna("ReceptorCurp", _nom("curp_receptor")),
    Columna("NumSeguridadSocial", _nom("num_seguridad_social")),
    Columna("NumEmpleado", _nom("num_empleado")),
    Columna("Departamento", _nom("departamento")),
    Columna("Puesto", _nom("puesto")),
    Columna("RiesgoPuesto", _nom("riesgo_puesto")),
    Columna("TipoContrato", _nom("tipo_contrato")),
    Columna("TipoRegimen", _nom("tipo_regimen")),
    Columna("TipoJornada", _nom("tipo_jornada")),
    Columna("Sindicalizado", _nom("sindicalizado")),
    Columna("PeriodicidadPago", _nom("periodicidad_pago")),
    Columna("Version Nomina", _nom("version")),
    Columna("TipoNomina", _nom("tipo_nomina")),
    Columna("FechaPago", _nom("fecha_pago", _fecha)),
    Columna("FechaInicialPago", _nom("fecha_inicial_pago", _fecha)),
    Columna("FechaFinalPago", _nom("fecha_final_pago", _fecha)),
    Columna("NumDiasPagados", _nom("num_dias_pagados", float)),
    Columna("FechaInicioRelLaboral", _nom("fecha_inicio_rel_laboral", _fecha)),
    Columna("Antigüedad", _nom("antiguedad")),
    Columna("Banco", _nom("banco")),
    Columna("CuentaBancaria", _nom("cuenta_bancaria")),
    Columna("ClaveEntFed", _nom("clave_ent_fed")),
    Columna("SalarioBaseCotApor", _nom("salario_base_cot_apor", float)),
    Columna("SalarioDiarioIntegrado", _nom("salario_diario_integrado", float)),
    Columna("TotalPercepciones", _nom("total_percepciones", float)),
    Columna("TotalDeducciones", _nom("total_deducciones", float)),
    Columna("TotalOtrosPagos", _nom("total_otros_pagos", float)),
    Columna("SubTotal", lambda f: float(f.cfdi.subtotal)),
    Columna("Descuento", lambda f: float(f.cfdi.descuento or 0)),
    Columna("Total", lambda f: float(f.cfdi.total)),
]

GRUPO_NOMINA = {"percepcion": "PERCEPCION", "deduccion": "DEDUCCION", "otro_pago": "OTRO PAGO"}

# Una fila por percepción/deducción: el reporte "solo conceptos" del despacho.
COLUMNAS_NOMINA_CONCEPTOS: list[Columna] = [
    Columna("Periodo", lambda f: f.cfdi.fecha.month),
    Columna("UUID", lambda f: f.cfdi.uuid_fiscal),
    Columna("Fecha emision", lambda f: _fecha(f.cfdi.fecha)),
    Columna("RFC Receptor", lambda f: f.cfdi.rfc_receptor),
    Columna("Nombre Receptor", lambda f: f.cfdi.nombre_receptor),
    Columna("NumEmpleado", _nom("num_empleado")),
    Columna("FechaPago", _nom("fecha_pago", _fecha)),
    Columna("Grupo", lambda f: GRUPO_NOMINA.get(getattr(f, "_concepto").grupo, "")),
    Columna("Tipo", lambda f: getattr(f, "_concepto").tipo_codigo or ""),
    Columna("Clave", lambda f: getattr(f, "_concepto").clave or ""),
    Columna("Concepto", lambda f: getattr(f, "_concepto").concepto),
    Columna("Gravado", lambda f: float(getattr(f, "_concepto").gravado)),
    Columna("Exento", lambda f: float(getattr(f, "_concepto").exento)),
    Columna("Importe", lambda f: float(getattr(f, "_concepto").gravado + getattr(f, "_concepto").exento)),
]

# --- Conciliación (MiAdminPro): factura contra lo efectivamente cobrado/pagado.
COLUMNAS_CONCILIACION: list[Columna] = [
    Columna("Periodo", lambda f: f.cfdi.fecha.month),
    Columna("Estado SAT", lambda f: ESTADO_SAT.get(f.cfdi.estatus, ""), sin_dato=False),
    Columna("Version", lambda f: f.cfdi.version or ""),
    Columna("TipoComprobante", lambda f: TIPO_SAT.get(f.cfdi.tipo_comprobante or "", "")),
    Columna("Fecha Emision", lambda f: _fecha(f.cfdi.fecha)),
    Columna("Fecha Timbrado", lambda f: _fecha(f.cfdi.fecha_timbrado)),
    Columna("Serie", lambda f: f.cfdi.serie or ""),
    Columna("Folio", lambda f: f.cfdi.folio or ""),
    Columna("UUID", lambda f: f.cfdi.uuid_fiscal),
    Columna("RFC Emisor", lambda f: f.cfdi.rfc_emisor),
    Columna("Nombre Emisor", lambda f: f.cfdi.nombre_emisor),
    Columna("RFC Receptor", lambda f: f.cfdi.rfc_receptor),
    Columna("Nombre Receptor", lambda f: f.cfdi.nombre_receptor),
    Columna("UsoCFDI", lambda f: f.cfdi.uso_cfdi_codigo or ""),
    Columna("Metodo de Pago", lambda f: f.cfdi.metodo_pago_codigo or ""),
    Columna("FormaDePago", lambda f: f.cfdi.forma_pago_codigo or ""),
    Columna("SubTotal", lambda f: float(f.cfdi.subtotal)),
    Columna("Descuento", lambda f: float(f.cfdi.descuento or 0)),
    Columna("IVA 16%", lambda f: _importe(f, "traslado", "002", Decimal("0.16"), factor="Tasa")),
    Columna("IVA 0%", lambda f: _importe(f, "traslado", "002", Decimal("0"), factor="Tasa")),
    Columna("IVA Exento", lambda f: _base(f, "traslado", "002", factor="Exento")),
    Columna("Retenido IVA", lambda f: float(f.cfdi.iva_retenido)),
    Columna("Retenido ISR", lambda f: float(f.cfdi.isr_retenido)),
    Columna("Total", lambda f: float(f.cfdi.total)),
    Columna("EstadoPago", _estado_pago),
    Columna("FechaPago", lambda f: _fecha(f.fecha_pago)),
    Columna("Importe pagado", lambda f: float(f.pagado)),
    Columna("Saldo Insoluto", lambda f: float(max(Decimal(f.cfdi.total) - f.pagado, Decimal("0")))),
    Columna("Resultado conciliacion", lambda f: _resultado_conciliacion(f)),
    Columna("Observaciones", lambda f: f.cfdi.pago_manual_nota or ""),
]


def _resultado_conciliacion(f: FilaCfdi) -> str:
    if f.cfdi.tipo not in ("ingreso", "egreso"):
        return ""
    total = Decimal(f.cfdi.total)
    if f.pagado <= 0:
        return "SIN CONCILIAR"
    if f.pagado >= total:
        return "CONCILIADO"
    return "PARCIAL"


FORMATOS = {
    "general": "CFDI con el layout del reporte general (ingresos y gastos), más las columnas del papel de trabajo",
    "comp": "Como el general pero con base e importe de cada tasa de IVA e IEPS por separado",
    "pagos": "Complementos de pago (REP): una fila por documento liquidado",
    "nomina": "Recibos de nómina: un recibo por fila con los datos del trabajador",
    "nomina_conceptos": "Nómina a detalle: una fila por percepción, deducción u otro pago",
    "conciliacion": "Factura contra lo efectivamente cobrado/pagado, con saldo insoluto",
}


# Formatos que solo tienen sentido sobre un tipo de comprobante. Se fuerza en la
# CONSULTA, no al armar las filas: si se filtrara después, el tope de filas se
# gastaría en CFDI que no van al reporte y se perderían recibos sin avisar.
# Los reportes de nómina llevan sueldos, CURP, NSS y cuenta bancaria de cada
# trabajador: no basta con poder ver CFDI para bajarlos.
PERMISO_EXTRA = {"nomina": "nomina.leer", "nomina_conceptos": "nomina.leer"}

TIPO_FORZADO = {"nomina": "nomina", "nomina_conceptos": "nomina", "pagos": "pago"}


def columnas_de(formato: str) -> list[Columna]:
    if formato == "pagos":
        return COLUMNAS_PAGOS + COLUMNAS_DOCTO
    if formato == "comp":
        # El desglose por tasa sustituye a las columnas de impuestos del general.
        base = [c for c in COLUMNAS_GENERAL if c.titulo not in COLUMNAS_IMPUESTOS_GENERAL]
        corte = [c.titulo for c in base].index("Total")
        return base[:corte] + _cols_tasas() + base[corte:] + COLUMNAS_TRABAJO
    if formato == "nomina":
        return COLUMNAS_NOMINA
    if formato == "nomina_conceptos":
        return COLUMNAS_NOMINA_CONCEPTOS
    if formato == "conciliacion":
        return COLUMNAS_CONCILIACION
    return COLUMNAS_GENERAL + COLUMNAS_TRABAJO


def construir(formato: str, filas: list[FilaCfdi]) -> tuple[list[str], list[list], list[str]]:
    """Devuelve (títulos, filas de valores, columnas que hoy salen vacías)."""
    columnas = columnas_de(formato)
    if formato in ("nomina", "nomina_conceptos"):
        filas = [f for f in filas if f.cfdi.tipo == "nomina"]
    if formato == "nomina_conceptos":
        expandidas: list[FilaCfdi] = []
        for f in filas:
            for c in (f.cfdi.nomina.conceptos if f.cfdi.nomina else ()):
                copia = FilaCfdi(cfdi=f.cfdi, fecha_pago=f.fecha_pago, uuid_pago=f.uuid_pago, pagado=f.pagado)
                copia._concepto = c  # type: ignore[attr-defined]
                expandidas.append(copia)
        filas = expandidas
    if formato == "pagos":
        expandidas: list[FilaCfdi] = []
        for f in filas:
            for d in f.cfdi.pagos_relacionados:
                copia = FilaCfdi(cfdi=f.cfdi, fecha_pago=d.fecha_pago, uuid_pago=f.cfdi.uuid_fiscal, pagado=d.imp_pagado)
                copia._docto = d  # type: ignore[attr-defined]
                expandidas.append(copia)
        filas = expandidas
    valores = [[c.valor(f) for c in columnas] for f in filas]
    return [c.titulo for c in columnas], valores, [c.titulo for c in columnas if c.sin_dato]
