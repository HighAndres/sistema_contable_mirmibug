"""CFDI reales: parser XML 4.0 (ingreso PUE/PPD, REP con Pagos 2.0, nómina, nota
de crédito), carga a la bóveda (dedupe, dirección por RFC, ajenos, ZIP), ligado
REP ↔ PPD en detalle, IVA en flujo y cuentas por cobrar."""

import io
import zipfile
from datetime import date
from decimal import Decimal

from app.modules.sat.xml_parser import XmlCfdiError, parse_cfdi_xml
from tests.conftest import agregar_membresia, auth_headers, crear_empresa, crear_usuario

EMPRESA = "NUB010101ABC"
CLIENTE = "CLI900101AA1"
PROVEEDOR = "PRO850505BB2"


def _cfdi(uuid, tipo="I", emisor=EMPRESA, receptor=CLIENTE, subtotal="10000.00", iva="1600.00", total="11600.00", metodo="PUE", forma="03", fecha="2026-08-05T10:00:00", extra="", conceptos=None, serie="A", folio="101", nombre_emisor="Nubinox Demo", nombre_receptor="Cliente Uno", impuestos=True):
    conceptos = conceptos or f'<cfdi:Concepto ClaveProdServ="80141600" Cantidad="2" ClaveUnidad="E48" Descripcion="Servicio de consultoría" ValorUnitario="5000.00" Importe="{subtotal}" ObjetoImp="02"><cfdi:Impuestos><cfdi:Traslados><cfdi:Traslado Base="{subtotal}" Impuesto="002" TipoFactor="Tasa" TasaOCuota="0.160000" Importe="{iva}"/></cfdi:Traslados></cfdi:Impuestos></cfdi:Concepto>'
    imp = f'<cfdi:Impuestos TotalImpuestosTrasladados="{iva}"><cfdi:Traslados><cfdi:Traslado Base="{subtotal}" Impuesto="002" TipoFactor="Tasa" TasaOCuota="0.160000" Importe="{iva}"/></cfdi:Traslados></cfdi:Impuestos>' if impuestos else ""
    metodo_attr = f' MetodoPago="{metodo}"' if metodo else ""
    forma_attr = f' FormaPago="{forma}"' if forma else ""
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/4" xmlns:tfd="http://www.sat.gob.mx/TimbreFiscalDigital" xmlns:pago20="http://www.sat.gob.mx/Pagos20" xmlns:nomina12="http://www.sat.gob.mx/nomina12" Version="4.0" Serie="{serie}" Folio="{folio}" Fecha="{fecha}"{forma_attr} SubTotal="{subtotal}" Moneda="MXN" Total="{total}" TipoDeComprobante="{tipo}" Exportacion="01"{metodo_attr} LugarExpedicion="07780" Sello="x" Certificado="x" NoCertificado="00001000000500000001">
  <cfdi:Emisor Rfc="{emisor}" Nombre="{nombre_emisor}" RegimenFiscal="601"/>
  <cfdi:Receptor Rfc="{receptor}" Nombre="{nombre_receptor}" DomicilioFiscalReceptor="06600" RegimenFiscalReceptor="601" UsoCFDI="G03"/>
  <cfdi:Conceptos>{conceptos}</cfdi:Conceptos>
  {imp}
  <cfdi:Complemento>{extra}
    <tfd:TimbreFiscalDigital Version="1.1" UUID="{uuid}" FechaTimbrado="{fecha}" RfcProvCertif="SAT970701NN3" SelloCFD="x" NoCertificadoSAT="00001000000504465028" SelloSAT="x"/>
  </cfdi:Complemento>
</cfdi:Comprobante>'''


UUID_PUE = "AAAAAAAA-1111-4111-8111-000000000001"
UUID_PPD = "AAAAAAAA-2222-4222-8222-000000000002"
UUID_REP = "AAAAAAAA-3333-4333-8333-000000000003"
UUID_NOM = "AAAAAAAA-4444-4444-8444-000000000004"
UUID_GASTO = "AAAAAAAA-5555-4555-8555-000000000005"
UUID_NC = "AAAAAAAA-6666-4666-8666-000000000006"
UUID_AJENO = "AAAAAAAA-7777-4777-8777-000000000007"

XML_PUE = _cfdi(UUID_PUE)
XML_PPD = _cfdi(UUID_PPD, metodo="PPD", forma="99", subtotal="20000.00", iva="3200.00", total="23200.00", folio="102", fecha="2026-08-06T09:00:00")
XML_REP = _cfdi(
    UUID_REP, tipo="P", subtotal="0", iva="0", total="0", metodo=None, forma=None, serie="P", folio="7", fecha="2026-08-20T12:00:00", impuestos=False,
    conceptos='<cfdi:Concepto ClaveProdServ="84111506" Cantidad="1" ClaveUnidad="ACT" Descripcion="Pago" ValorUnitario="0" Importe="0" ObjetoImp="01"/>',
    extra='''<pago20:Pagos Version="2.0"><pago20:Totales MontoTotalPagos="11600.00" TotalTrasladosBaseIVA16="10000.00" TotalTrasladosImpuestoIVA16="1600.00"/>
      <pago20:Pago FechaPago="2026-08-20T11:00:00" FormaDePagoP="03" MonedaP="MXN" TipoCambioP="1" Monto="11600.00">
        <pago20:DoctoRelacionado IdDocumento="AAAAAAAA-2222-4222-8222-000000000002" Serie="A" Folio="102" MonedaDR="MXN" EquivalenciaDR="1" NumParcialidad="1" ImpSaldoAnt="23200.00" ImpPagado="11600.00" ImpSaldoInsoluto="11600.00" ObjetoImpDR="02">
          <pago20:ImpuestosDR><pago20:TrasladosDR><pago20:TrasladoDR BaseDR="10000.00" ImpuestoDR="002" TipoFactorDR="Tasa" TasaOCuotaDR="0.160000" ImporteDR="1600.00"/></pago20:TrasladosDR></pago20:ImpuestosDR>
        </pago20:DoctoRelacionado>
        <pago20:ImpuestosP><pago20:TrasladosP><pago20:TrasladoP BaseP="10000.00" ImpuestoP="002" TipoFactorP="Tasa" TasaOCuotaP="0.160000" ImporteP="1600.00"/></pago20:TrasladosP></pago20:ImpuestosP>
      </pago20:Pago></pago20:Pagos>''',
)
XML_NOM = _cfdi(
    UUID_NOM, tipo="N", receptor="LORM850312MN1", nombre_receptor="María López", subtotal="9000.00", iva="0", total="8200.00", metodo="PUE", forma="99", serie="N", folio="55", fecha="2026-08-15T08:00:00", impuestos=False,
    conceptos='<cfdi:Concepto ClaveProdServ="84111505" Cantidad="1" ClaveUnidad="ACT" Descripcion="Pago de nómina" ValorUnitario="9000.00" Importe="9000.00" Descuento="800.00" ObjetoImp="01"/>',
    extra='<nomina12:Nomina Version="1.2" TipoNomina="O" FechaPago="2026-08-15" FechaInicialPago="2026-08-01" FechaFinalPago="2026-08-15" NumDiasPagados="15" TotalPercepciones="9000.00" TotalDeducciones="800.00"/>',
)
XML_GASTO = _cfdi(UUID_GASTO, emisor=PROVEEDOR, receptor=EMPRESA, nombre_emisor="Proveedor SA", nombre_receptor="Nubinox Demo", subtotal="3000.00", iva="480.00", total="3480.00", serie="F", folio="900", fecha="2026-08-10T10:00:00")
XML_NC = _cfdi(UUID_NC, tipo="E", subtotal="1000.00", iva="160.00", total="1160.00", serie="NC", folio="3", fecha="2026-08-25T10:00:00")
XML_AJENO = _cfdi(UUID_AJENO, emisor=PROVEEDOR, receptor=CLIENTE)


def test_parser_ingreso_pue_y_ppd():
    x = parse_cfdi_xml(XML_PUE.encode())
    assert x.uuid_fiscal == UUID_PUE and x.version == "4.0" and x.tipo_comprobante == "I"
    assert (x.serie, x.folio, x.metodo_pago_codigo, x.forma_pago_codigo) == ("A", "101", "PUE", "03")
    assert (x.subtotal, x.iva_trasladado, x.total) == (Decimal("10000.00"), Decimal("1600.00"), Decimal("11600.00"))
    assert x.rfc_emisor == EMPRESA and x.rfc_receptor == CLIENTE
    assert x.fecha.date() == date(2026, 8, 5) and x.fecha_timbrado is not None
    assert len(x.conceptos) == 1 and x.conceptos[0].clave_prodserv == "80141600" and x.conceptos[0].cantidad == 2
    assert x.direccion(EMPRESA) == "emitido" and x.tipo_interno("emitido") == "ingreso"
    assert x.direccion(CLIENTE) == "recibido" and x.tipo_interno("recibido") == "egreso"
    assert x.direccion("OTRO") is None


def test_parser_rep_pagos20_y_nomina_y_nota_credito():
    rep = parse_cfdi_xml(XML_REP.encode())
    assert rep.tipo_comprobante == "P" and rep.monto_pagos == Decimal("11600.00")
    assert len(rep.pagos) == 1
    d = rep.pagos[0]
    assert d.uuid_relacionado == UUID_PPD and d.num_parcialidad == 1
    assert (d.imp_saldo_anterior, d.imp_pagado, d.imp_saldo_insoluto, d.iva_pagado) == (Decimal("23200.00"), Decimal("11600.00"), Decimal("11600.00"), Decimal("1600.00"))
    assert d.fecha_pago == date(2026, 8, 20) and d.forma_pago_codigo == "03"
    assert rep.iva_trasladado == Decimal("1600.00")  # TrasladoP

    nom = parse_cfdi_xml(XML_NOM.encode())
    assert nom.tipo_comprobante == "N" and nom.nomina_percepciones == Decimal("9000.00") and nom.nomina_deducciones == Decimal("800.00")
    assert nom.tipo_interno("emitido") == "nomina"

    nc = parse_cfdi_xml(XML_NC.encode())
    assert nc.tipo_comprobante == "E" and nc.tipo_interno("emitido") == "nota_credito"


def test_parser_rechaza_xml_invalidos():
    for malo in (b"<html/>", b"no es xml", XML_PUE.replace('UUID="' + UUID_PUE + '"', "").encode(), XML_PUE.replace('Version="4.0"', 'Version="2.0"').encode()):
        try:
            parse_cfdi_xml(malo)
            assert False, "debió fallar"
        except XmlCfdiError:
            pass


def _setup(client, db, seed_rbac):
    usuario = crear_usuario(db)
    empresa = crear_empresa(db, rfc=EMPRESA, razon_social="Nubinox Demo")
    agregar_membresia(db, usuario=usuario, empresa=empresa, rol=seed_rbac["administrador"])
    return auth_headers(client, email=usuario.email, password="Demo1234!", empresa_id=empresa.id), empresa


def _zip(archivos: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for n, c in archivos.items():
            z.writestr(n, c)
    return buf.getvalue()


def test_carga_xml_zip_dedupe_ajenos_y_ligado_rep_ppd(client, seed_rbac, db):
    headers, empresa = _setup(client, db, seed_rbac)
    zipb = _zip({"pue.xml": XML_PUE, "ppd.xml": XML_PPD, "rep.xml": XML_REP, "nomina.xml": XML_NOM, "gasto.xml": XML_GASTO, "nc.xml": XML_NC, "ajeno.xml": XML_AJENO, "basura.xml": "<x/>", "leeme.txt": "no"})
    res = client.post(
        "/api/v1/sat/cargar-xml",
        headers=headers,
        files=[("archivos", ("agosto.zip", zipb, "application/zip")), ("archivos", ("pue_otra_vez.xml", XML_PUE.encode(), "application/xml"))],
    )
    assert res.status_code == 200, res.text
    r = res.json()
    assert (r["nuevos"], r["duplicados"], r["ajenos"]) == (6, 1, 1)
    assert any("basura.xml" in e["archivo"] for e in r["errores"]) and any("ajeno" in e["archivo"] for e in r["errores"])

    lista = client.get("/api/v1/cfdi?limit=100", headers=headers).json()["items"]
    por_uuid = {c["uuid_fiscal"]: c for c in lista}
    assert por_uuid[UUID_PUE]["tipo"] == "ingreso" and por_uuid[UUID_PUE]["direccion"] == "emitido" and por_uuid[UUID_PUE]["origen"] == "xml"
    assert por_uuid[UUID_GASTO]["tipo"] == "egreso" and por_uuid[UUID_GASTO]["direccion"] == "recibido" and por_uuid[UUID_GASTO]["nombre_emisor"] == "Proveedor SA"
    assert por_uuid[UUID_NOM]["tipo"] == "nomina" and por_uuid[UUID_NOM]["total"] == 8200
    assert por_uuid[UUID_NC]["tipo"] == "nota_credito" and por_uuid[UUID_NC]["tipo_comprobante"] == "E"
    # El REP guarda el monto pagado como total y el IVA de los documentos relacionados
    assert por_uuid[UUID_REP]["tipo"] == "pago" and por_uuid[UUID_REP]["total"] == 11600 and por_uuid[UUID_REP]["iva"] == 1600
    assert por_uuid[UUID_PPD]["metodo_pago_codigo"] == "PPD"

    # Detalle PPD: pagos recibidos y saldo pendiente = 23,200 − 11,600
    det = client.get(f"/api/v1/cfdi/{por_uuid[UUID_PPD]['id']}", headers=headers).json()
    assert len(det["pagos_recibidos"]) == 1 and det["pagos_recibidos"][0]["uuid_pago"] == UUID_REP
    assert det["saldo_pendiente"] == 11600 and det["tiene_xml"] is True
    det_rep = client.get(f"/api/v1/cfdi/{por_uuid[UUID_REP]['id']}", headers=headers).json()
    assert det_rep["pagos_relacionados"][0]["uuid_relacionado"] == UUID_PPD

    # XML original descargable
    xml = client.get(f"/api/v1/sat/xml/{por_uuid[UUID_PUE]['id']}", headers=headers)
    assert xml.status_code == 200 and UUID_PUE in xml.text

    # IVA agosto en flujo: PUE 1,600 + REP 1,600 − NC 160 = 3,040 trasladado; acreditable 480 (gasto PUE)
    iva = client.get("/api/v1/impuestos/iva?anio=2026&mes=8", headers=headers).json()
    assert iva["trasladado_cobrado"] == 3040 and iva["acreditable_pagado"] == 480
    # PPD pendiente: 23,200 − 11,600 pagados → base 10,000 / IVA 1,600
    ppd = next(f for f in iva["emitidas"] if f["concepto"] == "PPD pendiente")
    assert (ppd["num_cfdis"], ppd["base"], ppd["iva"]) == (1, 10000, 1600)
    nc = next(f for f in iva["emitidas"] if f["concepto"] == "Notas de crédito")
    assert nc["iva"] == 160

    # Cuentas por cobrar del dashboard descuentan lo pagado con REP
    dash = client.get("/api/v1/reports/dashboard?anio=2026&mes=8", headers=headers).json()
    assert dash["cuentas_por_cobrar"]["num_cfdis"] == 1 and dash["cuentas_por_cobrar"]["total"] == 11600

    # Resumen CFDI incluye notas de crédito
    resumen = client.get("/api/v1/cfdi/resumen?anio=2026", headers=headers).json()
    assert resumen["nota_credito"]["cantidad"] == 1 and resumen["pago"]["cantidad"] == 1


def test_carga_xml_sin_permiso(client, seed_rbac, db):
    usuario = crear_usuario(db)
    empresa = crear_empresa(db)
    agregar_membresia(db, usuario=usuario, empresa=empresa, rol=seed_rbac["contador"])
    headers = auth_headers(client, email=usuario.email, password="Demo1234!", empresa_id=empresa.id)
    # contador sí tiene sat.sincronizar → puede cargar; un XML de otra empresa se reporta como ajeno
    res = client.post("/api/v1/sat/cargar-xml", headers=headers, files=[("archivos", ("a.xml", XML_PUE.encode(), "application/xml"))])
    assert res.status_code == 200 and res.json()["ajenos"] == 1 and res.json()["nuevos"] == 0
