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

from app.modules.cfdi.models import (
    Cfdi,
    CfdiConcepto,
    CfdiImpuesto,
    CfdiNomina,
    CfdiNominaConcepto,
    CfdiPagoDocto,
    CfdiRelacionado,
)
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
        moneda=x.moneda[:3] if x.moneda else None,
        tipo_cambio=x.tipo_cambio,
        descuento=q2(x.descuento),
        regimen_emisor=x.regimen_emisor,
        regimen_receptor=x.regimen_receptor,
        lugar_expedicion=(x.lugar_expedicion or None) and x.lugar_expedicion[:10],
        domicilio_receptor=(x.domicilio_receptor or None) and x.domicilio_receptor[:10],
        exportacion=(x.exportacion or None) and x.exportacion[:10],
        condiciones_pago=(x.condiciones_pago or None) and x.condiciones_pago[:80],
        pac_rfc=(x.pac_rfc or None) and x.pac_rfc[:13],
        cuenta_predial=(x.cuenta_predial or None) and x.cuenta_predial[:150],
        complementos=", ".join(x.complementos)[:255] or None,
        global_periodicidad=x.global_periodicidad,
        global_meses=x.global_meses,
        global_anio=x.global_anio,
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
                clave_prodserv=(c.clave_prodserv or None) and c.clave_prodserv[:15],
                valor_unitario=c.valor_unitario,
                importe=c.importe,
            )
        )
    for i in x.impuestos:
        cfdi.impuestos.append(
            CfdiImpuesto(
                naturaleza=i.naturaleza,
                impuesto=i.impuesto[:10],
                tipo_factor=i.tipo_factor,
                tasa=i.tasa,
                base=q2(i.base),
                importe=q2(i.importe),
                nombre_local=(i.nombre_local or None) and i.nombre_local[:60],
            )
        )
    for r in x.relacionados:
        cfdi.relacionados.append(CfdiRelacionado(tipo_relacion=r.tipo_relacion, uuid_relacionado=r.uuid))
    if x.nomina is not None:
        n = x.nomina
        cfdi.nomina = CfdiNomina(
            version=n.version,
            tipo_nomina=n.tipo_nomina,
            fecha_pago=n.fecha_pago,
            fecha_inicial_pago=n.fecha_inicial_pago,
            fecha_final_pago=n.fecha_final_pago,
            num_dias_pagados=n.num_dias_pagados,
            total_percepciones=q2(n.total_percepciones),
            total_deducciones=q2(n.total_deducciones),
            total_otros_pagos=q2(n.total_otros_pagos),
            registro_patronal=n.registro_patronal,
            curp_emisor=n.curp_emisor,
            curp_receptor=n.curp_receptor,
            num_seguridad_social=n.num_seguridad_social,
            fecha_inicio_rel_laboral=n.fecha_inicio_rel_laboral,
            antiguedad=n.antiguedad,
            tipo_contrato=n.tipo_contrato,
            sindicalizado=n.sindicalizado,
            tipo_jornada=n.tipo_jornada,
            tipo_regimen=n.tipo_regimen,
            num_empleado=n.num_empleado,
            departamento=(n.departamento or None) and n.departamento[:100],
            puesto=(n.puesto or None) and n.puesto[:100],
            riesgo_puesto=n.riesgo_puesto,
            periodicidad_pago=n.periodicidad_pago,
            banco=n.banco,
            cuenta_bancaria=n.cuenta_bancaria,
            salario_base_cot_apor=n.salario_base_cot_apor,
            salario_diario_integrado=n.salario_diario_integrado,
            clave_ent_fed=n.clave_ent_fed,
            conceptos=[
                CfdiNominaConcepto(
                    grupo=c.grupo,
                    tipo_codigo=c.tipo_codigo,
                    clave=(c.clave or None) and c.clave[:15],
                    concepto=c.concepto or "(sin concepto)",
                    gravado=q2(c.gravado),
                    exento=q2(c.exento),
                )
                for c in n.conceptos
            ],
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
    """archivos: [(nombre, contenido)] — cada uno .xml o .zip con varios .xml.

    Se parsea todo primero y se consultan los UUID ya existentes de una sola vez:
    una carga de un ejercicio completo son miles de comprobantes y preguntar uno
    por uno era una consulta por archivo."""
    res = ResultadoCargaXml()
    parseados: list[tuple[str, CfdiXml]] = []
    for nombre, contenido in archivos:
        try:
            piezas = extraer_xmls(contenido, nombre)
        except XmlCfdiError as exc:
            res.errores.append({"archivo": nombre, "error": str(exc)})
            continue
        for nombre_xml, datos in piezas:
            try:
                parseados.append((nombre_xml, parse_cfdi_xml(datos)))
            except XmlCfdiError as exc:
                res.errores.append({"archivo": nombre_xml, "error": str(exc)})

    uuids = {x.uuid_fiscal for _, x in parseados}
    existentes = set(db.scalars(select(Cfdi.uuid_fiscal).where(Cfdi.uuid_fiscal.in_(uuids)))) if uuids else set()

    nuevos: list[Cfdi] = []
    vistos: set[str] = set()
    for nombre_xml, x in parseados:
        if x.uuid_fiscal in vistos or x.uuid_fiscal in existentes:
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
