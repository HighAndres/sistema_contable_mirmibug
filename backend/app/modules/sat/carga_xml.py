"""Carga de CFDI reales (XML / ZIP) a la bóveda de la empresa.

Es el mismo camino que usará la descarga masiva del SAT: parsear → clasificar
respecto a la empresa (emitido/recibido, tipo interno) → guardar con conceptos
y documentos relacionados de pago → correr el motor de reglas.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.cfdi.models import Cfdi, CfdiConcepto, CfdiPagoDocto
from app.modules.rules import crud as rules_crud
from app.modules.sat.xml_parser import CfdiXml, XmlCfdiError, extraer_xmls, parse_cfdi_xml
from app.modules.tenants.models import Empresa


@dataclass
class ResultadoCargaXml:
    nuevos: int = 0
    duplicados: int = 0
    ajenos: int = 0  # ni emisor ni receptor es la empresa
    errores: list[dict] = field(default_factory=list)  # {"archivo", "error"}
    alertas: int = 0
    uuids: list[str] = field(default_factory=list)


def _existe(db: Session, uuid_fiscal: str) -> bool:
    return db.scalar(select(Cfdi.id).where(Cfdi.uuid_fiscal == uuid_fiscal)) is not None


def guardar_cfdi(db: Session, *, empresa: Empresa, x: CfdiXml, origen: str = "xml") -> Cfdi | None:
    """Convierte el XML parseado en filas de la bóveda. None si es ajeno a la empresa."""
    direccion = x.direccion(empresa.rfc)
    if direccion is None:
        return None
    tipo = x.tipo_interno(direccion)
    # Los REP traen Total 0: para la bóveda guardamos como subtotal/total el
    # monto pagado y como IVA el trasladado de los documentos relacionados, así
    # los reportes en flujo (IVA, cuentas por cobrar) funcionan igual que con
    # facturas PUE.
    if x.tipo_comprobante == "P":
        total = x.monto_pagos
        iva = x.iva_trasladado
        subtotal = (total - iva) if total >= iva else total
    else:
        subtotal, iva, total = x.subtotal - x.descuento, x.iva_trasladado, x.total
        if x.moneda != "MXN" and x.tipo_cambio and x.tipo_cambio != 1:
            subtotal, iva, total = (subtotal * x.tipo_cambio, iva * x.tipo_cambio, total * x.tipo_cambio)

    q2 = lambda v: Decimal(v).quantize(Decimal("0.01"))  # noqa: E731
    cfdi = Cfdi(
        empresa_id=empresa.id,
        uuid_fiscal=x.uuid_fiscal,
        version=x.version[:5],
        serie=(x.serie or None) and x.serie[:25],
        folio=(x.folio or None) and x.folio[:40],
        tipo=tipo,
        tipo_comprobante=x.tipo_comprobante,
        direccion=direccion,
        rfc_emisor=x.rfc_emisor[:13],
        nombre_emisor=(x.nombre_emisor or x.rfc_emisor)[:255],
        rfc_receptor=x.rfc_receptor[:13],
        nombre_receptor=(x.nombre_receptor or x.rfc_receptor)[:255],
        forma_pago_codigo=x.forma_pago_codigo,
        metodo_pago_codigo=x.metodo_pago_codigo if x.tipo_comprobante in ("I", "E") else None,
        uso_cfdi_codigo=x.uso_cfdi_codigo,
        subtotal=q2(subtotal),
        iva=q2(iva),
        total=q2(total),
        iva_retenido=q2(x.iva_retenido),
        isr_retenido=q2(x.isr_retenido),
        fecha=x.fecha.date(),
        fecha_timbrado=x.fecha_timbrado,
        estatus="vigente",
        origen=origen,
        xml=x.xml_original,
    )
    for c in x.conceptos:
        cfdi.conceptos.append(
            CfdiConcepto(
                descripcion=c.descripcion or "(sin descripción)",
                cantidad=float(c.cantidad),
                unidad_codigo=c.unidad_codigo,
                valor_unitario=c.valor_unitario,
                importe=c.importe,
            )
        )
    for p in x.pagos:
        cfdi.pagos_relacionados.append(
            CfdiPagoDocto(
                uuid_relacionado=p.uuid_relacionado,
                serie=p.serie,
                folio=p.folio,
                num_parcialidad=p.num_parcialidad,
                imp_saldo_anterior=p.imp_saldo_anterior,
                imp_pagado=p.imp_pagado,
                imp_saldo_insoluto=p.imp_saldo_insoluto,
                iva_pagado=p.iva_pagado,
                fecha_pago=p.fecha_pago,
                forma_pago_codigo=p.forma_pago_codigo,
            )
        )
    db.add(cfdi)
    return cfdi


def cargar_archivos(db: Session, *, empresa: Empresa, archivos: list[tuple[str, bytes]]) -> ResultadoCargaXml:
    """archivos: [(nombre, contenido)] — cada uno .xml o .zip con varios .xml."""
    res = ResultadoCargaXml()
    nuevos: list[Cfdi] = []
    vistos: set[str] = set()
    for nombre, contenido in archivos:
        try:
            piezas = extraer_xmls(contenido, nombre)
        except XmlCfdiError as exc:
            res.errores.append({"archivo": nombre, "error": str(exc)})
            continue
        for nombre_xml, datos in piezas:
            try:
                x = parse_cfdi_xml(datos)
            except XmlCfdiError as exc:
                res.errores.append({"archivo": nombre_xml, "error": str(exc)})
                continue
            if x.uuid_fiscal in vistos or _existe(db, x.uuid_fiscal):
                res.duplicados += 1
                continue
            cfdi = guardar_cfdi(db, empresa=empresa, x=x)
            if cfdi is None:
                res.ajenos += 1
                res.errores.append({"archivo": nombre_xml, "error": f"El CFDI {x.uuid_fiscal[:8]}… no es de la empresa ({x.rfc_emisor} → {x.rfc_receptor}); se omitió"})
                continue
            vistos.add(x.uuid_fiscal)
            nuevos.append(cfdi)
            res.nuevos += 1
            res.uuids.append(x.uuid_fiscal)
    db.commit()
    for c in nuevos:
        db.refresh(c)
    res.alertas = rules_crud.evaluar_cfdis(db, nuevos) if nuevos else 0
    return res


def pagos_de_factura(db: Session, *, empresa_id: uuid.UUID, uuid_fiscal: str) -> list[CfdiPagoDocto]:
    """Complementos de pago (de la misma empresa) que pagan la factura dada."""
    return list(
        db.scalars(
            select(CfdiPagoDocto)
            .join(Cfdi, Cfdi.id == CfdiPagoDocto.cfdi_pago_id)
            .where(Cfdi.empresa_id == empresa_id, CfdiPagoDocto.uuid_relacionado == uuid_fiscal.upper(), Cfdi.estatus == "vigente")
            .order_by(CfdiPagoDocto.fecha_pago)
        )
    )
