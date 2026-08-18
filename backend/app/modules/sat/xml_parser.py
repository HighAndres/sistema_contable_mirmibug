"""Parser de CFDI reales (XML 4.0 y 3.3) a la estructura de la bóveda.

Lee lo que Nubinox necesita: comprobante, emisor/receptor, conceptos, impuestos
(IVA trasladado y retenciones), Timbre Fiscal Digital (UUID, fecha de
timbrado) y los complementos de **Pagos** (2.0 / 1.0: qué facturas PPD paga y
cuánto) y **Nómina** (1.2: percepciones/deducciones como totales). Con eso el
sistema puede ligar REP ↔ factura PPD, que es la base del IVA en flujo y de las
cuentas por cobrar/pagar.

No valida el sello ni consulta el estatus en el SAT (eso es de la etapa con
conexión real). Tolera espacios de nombres distintos entre versiones.
"""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from xml.etree import ElementTree as ET

NS = {
    "cfdi4": "http://www.sat.gob.mx/cfd/4",
    "cfdi3": "http://www.sat.gob.mx/cfd/3",
    "tfd": "http://www.sat.gob.mx/TimbreFiscalDigital",
    "pago20": "http://www.sat.gob.mx/Pagos20",
    "pago10": "http://www.sat.gob.mx/Pagos",
    "nomina12": "http://www.sat.gob.mx/nomina12",
}

# Letra del SAT → tipo interno (según dirección respecto a la empresa)
TIPO_COMPROBANTE = {"I": "ingreso", "E": "nota_credito", "P": "pago", "N": "nomina", "T": "traslado"}


class XmlCfdiError(ValueError):
    pass


def _dec(v: str | None, default: Decimal = Decimal("0")) -> Decimal:
    if v is None or v == "":
        return default
    try:
        return Decimal(v)
    except InvalidOperation as exc:
        raise XmlCfdiError(f"Número inválido en el XML: {v!r}") from exc


def _fecha(v: str | None) -> datetime | None:
    if not v:
        return None
    try:
        return datetime.fromisoformat(v)
    except ValueError:
        return None


@dataclass
class ConceptoXml:
    descripcion: str
    cantidad: Decimal
    unidad_codigo: str | None
    clave_prodserv: str | None
    valor_unitario: Decimal
    importe: Decimal


@dataclass
class DoctoPagoXml:
    uuid_relacionado: str
    serie: str | None
    folio: str | None
    num_parcialidad: int | None
    imp_saldo_anterior: Decimal | None
    imp_pagado: Decimal
    imp_saldo_insoluto: Decimal | None
    iva_pagado: Decimal
    fecha_pago: date | None
    forma_pago_codigo: str | None


@dataclass
class CfdiXml:
    uuid_fiscal: str
    version: str
    tipo_comprobante: str  # I E P N T
    serie: str | None
    folio: str | None
    fecha: datetime
    fecha_timbrado: datetime | None
    rfc_emisor: str
    nombre_emisor: str
    regimen_emisor: str | None
    rfc_receptor: str
    nombre_receptor: str
    uso_cfdi_codigo: str | None
    forma_pago_codigo: str | None
    metodo_pago_codigo: str | None
    moneda: str
    tipo_cambio: Decimal
    subtotal: Decimal
    descuento: Decimal
    total: Decimal
    iva_trasladado: Decimal
    iva_retenido: Decimal
    isr_retenido: Decimal
    conceptos: list[ConceptoXml] = field(default_factory=list)
    pagos: list[DoctoPagoXml] = field(default_factory=list)  # solo tipo P
    monto_pagos: Decimal = Decimal("0")  # Σ Pago@Monto (tipo P)
    nomina_percepciones: Decimal | None = None
    nomina_deducciones: Decimal | None = None
    xml_original: str = ""

    def direccion(self, rfc_empresa: str) -> str | None:
        rfc = rfc_empresa.strip().upper()
        if self.rfc_emisor.upper() == rfc:
            return "emitido"
        if self.rfc_receptor.upper() == rfc:
            return "recibido"
        return None

    def tipo_interno(self, direccion: str) -> str:
        base = TIPO_COMPROBANTE.get(self.tipo_comprobante, "ingreso")
        if base == "ingreso":
            return "ingreso" if direccion == "emitido" else "egreso"
        return base


def _localname(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _find_children(el: ET.Element, nombre: str) -> list[ET.Element]:
    return [c for c in el if _localname(c.tag) == nombre]


def _find_child(el: ET.Element, nombre: str) -> ET.Element | None:
    hijos = _find_children(el, nombre)
    return hijos[0] if hijos else None


def _iter_desc(el: ET.Element, nombre: str):
    for e in el.iter():
        if _localname(e.tag) == nombre:
            yield e


def parse_cfdi_xml(contenido: bytes | str) -> CfdiXml:
    texto = contenido.decode("utf-8-sig") if isinstance(contenido, bytes) else contenido
    try:
        root = ET.fromstring(texto)
    except ET.ParseError as exc:
        raise XmlCfdiError(f"XML mal formado: {exc}") from exc
    if _localname(root.tag) != "Comprobante":
        raise XmlCfdiError("El XML no es un CFDI (raíz distinta de cfdi:Comprobante)")

    a = root.attrib
    version = a.get("Version") or a.get("version") or ""
    if not version.startswith(("3.3", "4.")):
        raise XmlCfdiError(f"Versión de CFDI no soportada: {version!r} (se aceptan 3.3 y 4.0)")

    emisor = _find_child(root, "Emisor")
    receptor = _find_child(root, "Receptor")
    if emisor is None or receptor is None:
        raise XmlCfdiError("El CFDI no trae Emisor o Receptor")

    tfd = next(iter(_iter_desc(root, "TimbreFiscalDigital")), None)
    if tfd is None or not tfd.attrib.get("UUID"):
        raise XmlCfdiError("El CFDI no está timbrado (falta TimbreFiscalDigital/UUID)")

    fecha = _fecha(a.get("Fecha"))
    if fecha is None:
        raise XmlCfdiError("Fecha del comprobante inválida")

    # Impuestos a nivel comprobante (4.0: cfdi:Impuestos hijo directo, con Traslados/Retenciones)
    iva_tras = iva_ret = isr_ret = Decimal("0")
    imp = _find_child(root, "Impuestos")
    if imp is not None:
        for t in _iter_desc(imp, "Traslado"):
            if t.attrib.get("Impuesto") == "002":
                iva_tras += _dec(t.attrib.get("Importe"))
        for r in _iter_desc(imp, "Retencion"):
            if r.attrib.get("Impuesto") == "002":
                iva_ret += _dec(r.attrib.get("Importe"))
            elif r.attrib.get("Impuesto") == "001":
                isr_ret += _dec(r.attrib.get("Importe"))

    conceptos: list[ConceptoXml] = []
    conc_el = _find_child(root, "Conceptos")
    if conc_el is not None:
        for c in _find_children(conc_el, "Concepto"):
            ca = c.attrib
            conceptos.append(
                ConceptoXml(
                    descripcion=(ca.get("Descripcion") or "")[:255],
                    cantidad=_dec(ca.get("Cantidad"), Decimal("1")),
                    unidad_codigo=ca.get("ClaveUnidad"),
                    clave_prodserv=ca.get("ClaveProdServ"),
                    valor_unitario=_dec(ca.get("ValorUnitario")),
                    importe=_dec(ca.get("Importe")),
                )
            )

    cfdi = CfdiXml(
        uuid_fiscal=tfd.attrib["UUID"].upper(),
        version=version,
        tipo_comprobante=(a.get("TipoDeComprobante") or "I").upper(),
        serie=a.get("Serie"),
        folio=a.get("Folio"),
        fecha=fecha,
        fecha_timbrado=_fecha(tfd.attrib.get("FechaTimbrado")),
        rfc_emisor=(emisor.attrib.get("Rfc") or emisor.attrib.get("rfc") or "").upper(),
        nombre_emisor=emisor.attrib.get("Nombre") or emisor.attrib.get("nombre") or "",
        regimen_emisor=emisor.attrib.get("RegimenFiscal"),
        rfc_receptor=(receptor.attrib.get("Rfc") or receptor.attrib.get("rfc") or "").upper(),
        nombre_receptor=receptor.attrib.get("Nombre") or receptor.attrib.get("nombre") or "",
        uso_cfdi_codigo=receptor.attrib.get("UsoCFDI"),
        forma_pago_codigo=a.get("FormaPago"),
        metodo_pago_codigo=a.get("MetodoPago"),
        moneda=a.get("Moneda") or "MXN",
        tipo_cambio=_dec(a.get("TipoCambio"), Decimal("1")),
        subtotal=_dec(a.get("SubTotal")),
        descuento=_dec(a.get("Descuento")),
        total=_dec(a.get("Total")),
        iva_trasladado=iva_tras,
        iva_retenido=iva_ret,
        isr_retenido=isr_ret,
        conceptos=conceptos,
        xml_original=texto,
    )

    # ---- Complemento de pagos ----
    if cfdi.tipo_comprobante == "P":
        for pago in _iter_desc(root, "Pago"):
            pa = pago.attrib
            fecha_pago = _fecha(pa.get("FechaPago"))
            cfdi.monto_pagos += _dec(pa.get("Monto"))
            for d in _find_children(pago, "DoctoRelacionado"):
                da = d.attrib
                iva_docto = Decimal("0")
                for t in _iter_desc(d, "TrasladoDR"):
                    if t.attrib.get("ImpuestoDR") == "002":
                        iva_docto += _dec(t.attrib.get("ImporteDR"))
                parc = da.get("NumParcialidad")
                cfdi.pagos.append(
                    DoctoPagoXml(
                        uuid_relacionado=(da.get("IdDocumento") or "").upper(),
                        serie=da.get("Serie"),
                        folio=da.get("Folio"),
                        num_parcialidad=int(parc) if parc and parc.isdigit() else None,
                        imp_saldo_anterior=_dec(da.get("ImpSaldoAnt")) if da.get("ImpSaldoAnt") else None,
                        imp_pagado=_dec(da.get("ImpPagado")),
                        imp_saldo_insoluto=_dec(da.get("ImpSaldoInsoluto")) if da.get("ImpSaldoInsoluto") else None,
                        iva_pagado=iva_docto,
                        fecha_pago=fecha_pago.date() if fecha_pago else None,
                        forma_pago_codigo=pa.get("FormaDePagoP"),
                    )
                )
        # Los REP no llevan impuestos a nivel comprobante; el IVA "cobrado" es el
        # de los documentos relacionados (TrasladoDR) o, en Pagos 2.0, TrasladoP.
        if cfdi.iva_trasladado == 0:
            iva_p = Decimal("0")
            for t in _iter_desc(root, "TrasladoP"):
                if t.attrib.get("ImpuestoP") == "002":
                    iva_p += _dec(t.attrib.get("ImporteP"))
            cfdi.iva_trasladado = iva_p or sum((p.iva_pagado for p in cfdi.pagos), Decimal("0"))

    # ---- Complemento de nómina ----
    if cfdi.tipo_comprobante == "N":
        nom = next(iter(_iter_desc(root, "Nomina")), None)
        if nom is not None:
            cfdi.nomina_percepciones = _dec(nom.attrib.get("TotalPercepciones")) if nom.attrib.get("TotalPercepciones") else None
            cfdi.nomina_deducciones = _dec(nom.attrib.get("TotalDeducciones")) if nom.attrib.get("TotalDeducciones") else None

    return cfdi


def extraer_xmls(contenido: bytes, nombre_archivo: str) -> list[tuple[str, bytes]]:
    """Devuelve [(nombre, bytes)] de XML: acepta un .xml suelto o un .zip con varios."""
    nombre = (nombre_archivo or "").lower()
    if nombre.endswith(".zip") or contenido[:2] == b"PK":
        try:
            zf = zipfile.ZipFile(io.BytesIO(contenido))
        except zipfile.BadZipFile as exc:
            raise XmlCfdiError("El archivo ZIP está dañado") from exc
        out = []
        for info in zf.infolist():
            if info.is_dir() or not info.filename.lower().endswith(".xml") or info.filename.startswith("__MACOSX"):
                continue
            out.append((info.filename, zf.read(info)))
        return out
    return [(nombre_archivo, contenido)]
