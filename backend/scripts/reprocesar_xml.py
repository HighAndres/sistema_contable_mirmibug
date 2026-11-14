"""Reprocesa los XML ya guardados en la bóveda para rellenar lo que el parser
de su época no guardaba: desglose de impuestos por tasa (cfdi_impuestos), CFDI
relacionados, complemento de nómina (cfdi_nominas y sus conceptos), documentos
de pago de un REP, clave SAT de los conceptos y las columnas del comprobante
que estrenaron los reportes (moneda, regímenes, lugar de expedición, PAC…).

Es idempotente y NUNCA pisa lo que ya existe:
- Las cifras del comprobante (subtotal, IVA, total, estatus) no se tocan.
- Lo capturado por el contador (clasificación, pago manual) no se toca.
- Los desgloses (impuestos, relacionados, nómina, pagos) solo se insertan si
  el CFDI no tiene ninguno.
- Las columnas sueltas solo se llenan si están vacías.
- Los conceptos solo se reescriben si a TODOS les falta la clave SAT (eran de
  una carga vieja) y el XML sí la trae.

Uso:
    PYTHONPATH=. .venv/bin/python scripts/reprocesar_xml.py [--dry-run] [--empresa RFC]
"""

from __future__ import annotations

import argparse
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.modules.cfdi.models import (
    Cfdi,
    CfdiConcepto,
    CfdiImpuesto,
    CfdiNomina,
    CfdiNominaConcepto,
    CfdiPagoDocto,
    CfdiRelacionado,
)
from app.modules.sat.xml_parser import XmlCfdiError, parse_cfdi_xml
from app.modules.tenants.models import Empresa

LOTE = 200

#: Columnas del comprobante que se completan SOLO si están vacías, con el
#: atributo equivalente del XML parseado (mismo recorte que en carga_xml).
COLUMNAS = {
    "version": lambda x: x.version[:5],
    "tipo_comprobante": lambda x: x.tipo_comprobante,
    "uso_cfdi_codigo": lambda x: x.uso_cfdi_codigo,
    "forma_pago_codigo": lambda x: x.forma_pago_codigo,
    "moneda": lambda x: x.moneda[:3] if x.moneda else None,
    "tipo_cambio": lambda x: x.tipo_cambio,
    "regimen_emisor": lambda x: x.regimen_emisor,
    "regimen_receptor": lambda x: x.regimen_receptor,
    "lugar_expedicion": lambda x: (x.lugar_expedicion or None) and x.lugar_expedicion[:10],
    "domicilio_receptor": lambda x: (x.domicilio_receptor or None) and x.domicilio_receptor[:10],
    "exportacion": lambda x: (x.exportacion or None) and x.exportacion[:10],
    "condiciones_pago": lambda x: (x.condiciones_pago or None) and x.condiciones_pago[:80],
    "pac_rfc": lambda x: (x.pac_rfc or None) and x.pac_rfc[:13],
    "cuenta_predial": lambda x: (x.cuenta_predial or None) and x.cuenta_predial[:150],
    "complementos": lambda x: ", ".join(x.complementos)[:255] or None,
    "global_periodicidad": lambda x: x.global_periodicidad,
    "global_meses": lambda x: x.global_meses,
    "global_anio": lambda x: x.global_anio,
    "fecha_timbrado": lambda x: x.fecha_timbrado,
}


def q2(v) -> Decimal:
    return Decimal(v).quantize(Decimal("0.01"))


def reprocesar_cfdi(cfdi: Cfdi) -> dict:
    """Rellena lo que falte en un CFDI a partir de su XML guardado. Devuelve qué
    hizo; no commitea (el que llama decide el lote)."""
    hecho = {"columnas": 0, "impuestos": False, "relacionados": False, "nomina": False, "pagos": False, "conceptos": False, "descuento": False}
    x = parse_cfdi_xml(cfdi.xml)

    for columna, valor_de in COLUMNAS.items():
        if getattr(cfdi, columna) is None:
            valor = valor_de(x)
            # El método de pago de un REP/nómina se queda nulo a propósito
            # (igual que en la carga), así que no cuenta como "faltante".
            if valor is not None:
                setattr(cfdi, columna, valor)
                hecho["columnas"] += 1
    if cfdi.descuento in (None, 0) and x.descuento:
        cfdi.descuento = q2(x.descuento)
        hecho["descuento"] = True

    if not cfdi.impuestos and x.impuestos:
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
        hecho["impuestos"] = True

    if not cfdi.relacionados and x.relacionados:
        for r in x.relacionados:
            cfdi.relacionados.append(CfdiRelacionado(tipo_relacion=r.tipo_relacion, uuid_relacionado=r.uuid))
        hecho["relacionados"] = True

    if cfdi.nomina is None and x.nomina is not None:
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
        hecho["nomina"] = True

    if not cfdi.pagos_relacionados and x.pagos:
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
        hecho["pagos"] = True

    # Conceptos: solo si TODOS vienen sin clave SAT (carga vieja) y el XML sí
    # la trae en alguno. Se reescriben completos para que queden idénticos a
    # una carga nueva; nadie captura nada sobre un concepto, así que es seguro.
    if cfdi.conceptos and all(c.clave_prodserv is None for c in cfdi.conceptos) and any(c.clave_prodserv for c in x.conceptos):
        cfdi.conceptos.clear()
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
        hecho["conceptos"] = True

    return hecho


def reprocesar(db: Session, *, empresa_rfc: str | None = None, dry_run: bool = False) -> dict:
    stmt = select(Cfdi.id).where(Cfdi.xml.is_not(None)).order_by(Cfdi.created_at)
    if empresa_rfc:
        empresa = db.scalar(select(Empresa).where(Empresa.rfc == empresa_rfc.upper()))
        if empresa is None:
            raise SystemExit(f"No existe una empresa con RFC {empresa_rfc}")
        stmt = stmt.where(Cfdi.empresa_id == empresa.id)
    ids = list(db.scalars(stmt))

    totales = {"procesados": 0, "con_cambios": 0, "columnas": 0, "impuestos": 0, "relacionados": 0, "nomina": 0, "pagos": 0, "conceptos": 0, "errores": []}
    pendientes = 0
    for cfdi_id in ids:
        cfdi = db.get(Cfdi, cfdi_id)
        try:
            hecho = reprocesar_cfdi(cfdi)
        except XmlCfdiError as exc:
            totales["errores"].append({"uuid": cfdi.uuid_fiscal, "error": str(exc)})
            db.expunge(cfdi)
            continue
        totales["procesados"] += 1
        cambio = hecho["columnas"] > 0 or any(v is True for v in hecho.values())
        if cambio:
            totales["con_cambios"] += 1
            totales["columnas"] += hecho["columnas"]
            for k in ("impuestos", "relacionados", "nomina", "pagos", "conceptos"):
                totales[k] += int(hecho[k])
            pendientes += 1
        if pendientes >= LOTE:
            db.rollback() if dry_run else db.commit()
            pendientes = 0
    db.rollback() if dry_run else db.commit()
    return totales


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--empresa", help="RFC de una sola empresa (vacío = todas)")
    parser.add_argument("--dry-run", action="store_true", help="Cuenta qué haría sin guardar nada")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        t = reprocesar(db, empresa_rfc=args.empresa, dry_run=args.dry_run)
    finally:
        db.close()
    modo = "(simulación, nada guardado)" if args.dry_run else ""
    print(f"Reproceso {modo}: {t['procesados']} CFDI con XML, {t['con_cambios']} con algo que rellenar.")
    print(
        f"  Desgloses de impuestos: {t['impuestos']} · nóminas: {t['nomina']} · relacionados: {t['relacionados']}"
        f" · pagos REP: {t['pagos']} · conceptos reescritos: {t['conceptos']} · columnas sueltas: {t['columnas']}"
    )
    for e in t["errores"][:20]:
        print(f"  ERROR {e['uuid'][:13]}…: {e['error']}")
    if len(t["errores"]) > 20:
        print(f"  … y {len(t['errores']) - 20} errores más")


if __name__ == "__main__":
    main()
