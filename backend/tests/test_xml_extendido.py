"""Lo que el parser tenía que aprender a leer para cubrir los reportes del
despacho: impuestos por tasa (IVA/IEPS/exento/no objeto/locales), CFDI
relacionados, complementos incorporados, CFDI global y complemento de nómina.
"""

from decimal import Decimal

from app.modules.cfdi.models import Cfdi
from app.modules.sat.xml_parser import parse_cfdi_xml
from tests.conftest import agregar_membresia, auth_headers, crear_empresa, crear_usuario

EMPRESA = "NUB010101ABC"
CLIENTE = "CLI900101AA1"

UUID_MIXTO = "BBBBBBBB-1111-4111-8111-000000000001"
UUID_RELACIONADA = "BBBBBBBB-9999-4999-8999-000000000009"
UUID_GLOBAL = "BBBBBBBB-2222-4222-8222-000000000002"
UUID_NOMINA = "BBBBBBBB-3333-4333-8333-000000000003"

# Factura con tres tasas distintas, un concepto no objeto, retenciones,
# impuestos locales y una relación con otro CFDI.
XML_MIXTO = f"""<?xml version="1.0" encoding="UTF-8"?>
<cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/4" xmlns:tfd="http://www.sat.gob.mx/TimbreFiscalDigital" xmlns:implocal="http://www.sat.gob.mx/implocal"
  Version="4.0" Serie="A" Folio="500" Fecha="2026-08-05T10:00:00" FormaPago="03" SubTotal="10500.00" Moneda="MXN" TipoCambio="1"
  Total="11294.00" TipoDeComprobante="I" Exportacion="01" MetodoPago="PUE" LugarExpedicion="07780" CondicionesDePago="30 dias"
  Sello="x" Certificado="x" NoCertificado="00001000000500000001">
  <cfdi:CfdiRelacionados TipoRelacion="04">
    <cfdi:CfdiRelacionado UUID="{UUID_RELACIONADA}"/>
  </cfdi:CfdiRelacionados>
  <cfdi:Emisor Rfc="{EMPRESA}" Nombre="Nubinox Demo" RegimenFiscal="601"/>
  <cfdi:Receptor Rfc="{CLIENTE}" Nombre="Cliente Uno" DomicilioFiscalReceptor="06600" RegimenFiscalReceptor="601" UsoCFDI="G03"/>
  <cfdi:Conceptos>
    <cfdi:Concepto ClaveProdServ="80141600" Cantidad="1" ClaveUnidad="E48" Descripcion="Consultoría" ValorUnitario="5000.00" Importe="5000.00" ObjetoImp="02">
      <cfdi:Impuestos>
        <cfdi:Traslados><cfdi:Traslado Base="5000.00" Impuesto="002" TipoFactor="Tasa" TasaOCuota="0.160000" Importe="800.00"/></cfdi:Traslados>
        <cfdi:Retenciones><cfdi:Retencion Base="5000.00" Impuesto="001" TipoFactor="Tasa" TasaOCuota="0.100000" Importe="500.00"/></cfdi:Retenciones>
      </cfdi:Impuestos>
    </cfdi:Concepto>
    <cfdi:Concepto ClaveProdServ="50202306" Cantidad="1" ClaveUnidad="H87" Descripcion="Refresco" ValorUnitario="3000.00" Importe="3000.00" ObjetoImp="02">
      <cfdi:Impuestos>
        <cfdi:Traslados>
          <cfdi:Traslado Base="3000.00" Impuesto="003" TipoFactor="Tasa" TasaOCuota="0.030000" Importe="90.00"/>
          <cfdi:Traslado Base="3090.00" Impuesto="002" TipoFactor="Tasa" TasaOCuota="0.080000" Importe="247.20"/>
        </cfdi:Traslados>
      </cfdi:Impuestos>
    </cfdi:Concepto>
    <cfdi:Concepto ClaveProdServ="01010101" Cantidad="1" ClaveUnidad="E48" Descripcion="Medicinas" ValorUnitario="1500.00" Importe="1500.00" ObjetoImp="02">
      <cfdi:Impuestos>
        <cfdi:Traslados><cfdi:Traslado Base="1500.00" Impuesto="002" TipoFactor="Exento"/></cfdi:Traslados>
      </cfdi:Impuestos>
    </cfdi:Concepto>
    <cfdi:Concepto ClaveProdServ="84111506" Cantidad="1" ClaveUnidad="E48" Descripcion="Cuota" ValorUnitario="1000.00" Importe="1000.00" ObjetoImp="01">
      <cfdi:CuentaPredial Numero="1234567890"/>
    </cfdi:Concepto>
  </cfdi:Conceptos>
  <cfdi:Impuestos TotalImpuestosTrasladados="1137.20" TotalImpuestosRetenidos="500.00"/>
  <cfdi:Complemento>
    <implocal:ImpuestosLocales version="1.0" TotaldeRetenciones="0.00" TotaldeTraslados="105.00">
      <implocal:TrasladosLocales ImpLocTrasladado="ISH" TasadeTraslado="3.00" Importe="105.00"/>
    </implocal:ImpuestosLocales>
    <tfd:TimbreFiscalDigital Version="1.1" UUID="{UUID_MIXTO}" FechaTimbrado="2026-08-05T10:05:00" RfcProvCertifica="SAT970701NN3" SelloCFD="x" NoCertificadoSAT="00001000000504465028" SelloSAT="x"/>
  </cfdi:Complemento>
</cfdi:Comprobante>"""

XML_GLOBAL = f"""<?xml version="1.0" encoding="UTF-8"?>
<cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/4" xmlns:tfd="http://www.sat.gob.mx/TimbreFiscalDigital"
  Version="4.0" Serie="G" Folio="1" Fecha="2026-08-31T23:00:00" FormaPago="01" SubTotal="1000.00" Moneda="MXN"
  Total="1160.00" TipoDeComprobante="I" Exportacion="01" MetodoPago="PUE" LugarExpedicion="07780"
  Sello="x" Certificado="x" NoCertificado="00001000000500000001">
  <cfdi:InformacionGlobal Periodicidad="04" Meses="08" Año="2026"/>
  <cfdi:Emisor Rfc="{EMPRESA}" Nombre="Nubinox Demo" RegimenFiscal="601"/>
  <cfdi:Receptor Rfc="XAXX010101000" Nombre="PUBLICO EN GENERAL" DomicilioFiscalReceptor="07780" RegimenFiscalReceptor="616" UsoCFDI="S01"/>
  <cfdi:Conceptos>
    <cfdi:Concepto ClaveProdServ="01010101" Cantidad="1" ClaveUnidad="ACT" Descripcion="Venta" ValorUnitario="1000.00" Importe="1000.00" ObjetoImp="02">
      <cfdi:Impuestos><cfdi:Traslados><cfdi:Traslado Base="1000.00" Impuesto="002" TipoFactor="Tasa" TasaOCuota="0.160000" Importe="160.00"/></cfdi:Traslados></cfdi:Impuestos>
    </cfdi:Concepto>
  </cfdi:Conceptos>
  <cfdi:Complemento>
    <tfd:TimbreFiscalDigital Version="1.1" UUID="{UUID_GLOBAL}" FechaTimbrado="2026-08-31T23:05:00" RfcProvCertifica="SAT970701NN3" SelloCFD="x" NoCertificadoSAT="1" SelloSAT="x"/>
  </cfdi:Complemento>
</cfdi:Comprobante>"""

XML_NOMINA = f"""<?xml version="1.0" encoding="UTF-8"?>
<cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/4" xmlns:tfd="http://www.sat.gob.mx/TimbreFiscalDigital" xmlns:nomina12="http://www.sat.gob.mx/nomina12"
  Version="4.0" Serie="N" Folio="77" Fecha="2026-08-15T10:00:00" FormaPago="99" SubTotal="12000.00" Descuento="2000.00" Moneda="MXN"
  Total="10000.00" TipoDeComprobante="N" Exportacion="01" LugarExpedicion="07780" Sello="x" Certificado="x" NoCertificado="1">
  <cfdi:Emisor Rfc="{EMPRESA}" Nombre="Nubinox Demo" RegimenFiscal="601"/>
  <cfdi:Receptor Rfc="EMPL800101AB1" Nombre="Juan Perez" DomicilioFiscalReceptor="07780" RegimenFiscalReceptor="605" UsoCFDI="CN01"/>
  <cfdi:Conceptos>
    <cfdi:Concepto ClaveProdServ="84111505" Cantidad="1" ClaveUnidad="ACT" Descripcion="Pago de nómina" ValorUnitario="12000.00" Importe="12000.00" Descuento="2000.00" ObjetoImp="01"/>
  </cfdi:Conceptos>
  <cfdi:Complemento>
    <nomina12:Nomina Version="1.2" TipoNomina="O" FechaPago="2026-08-15" FechaInicialPago="2026-08-01" FechaFinalPago="2026-08-15"
      NumDiasPagados="15" TotalPercepciones="12000.00" TotalDeducciones="2000.00" TotalOtrosPagos="150.00">
      <nomina12:Emisor RegistroPatronal="B5510768108"/>
      <nomina12:Receptor Curp="PEPJ800101HDFRRN09" NumSeguridadSocial="12345678901" FechaInicioRelLaboral="2020-03-01"
        Antigüedad="P5Y" TipoContrato="01" Sindicalizado="No" TipoJornada="01" TipoRegimen="02" NumEmpleado="0042"
        Departamento="Operaciones" Puesto="Analista" RiesgoPuesto="1" PeriodicidadPago="04" Banco="002" CuentaBancaria="0123456789"
        SalarioBaseCotApor="400.00" SalarioDiarioIntegrado="420.00" ClaveEntFed="DIF"/>
      <nomina12:Percepciones TotalSueldos="12000.00" TotalGravado="11000.00" TotalExento="1000.00">
        <nomina12:Percepcion TipoPercepcion="001" Clave="P001" Concepto="Sueldos" ImporteGravado="11000.00" ImporteExento="1000.00"/>
      </nomina12:Percepciones>
      <nomina12:Deducciones TotalOtrasDeducciones="500.00" TotalImpuestosRetenidos="1500.00">
        <nomina12:Deduccion TipoDeduccion="002" Clave="D002" Concepto="ISR" Importe="1500.00"/>
        <nomina12:Deduccion TipoDeduccion="001" Clave="D001" Concepto="IMSS" Importe="500.00"/>
      </nomina12:Deducciones>
      <nomina12:OtrosPagos>
        <nomina12:OtroPago TipoOtroPago="002" Clave="O002" Concepto="Subsidio" Importe="150.00"/>
      </nomina12:OtrosPagos>
    </nomina12:Nomina>
    <tfd:TimbreFiscalDigital Version="1.1" UUID="{UUID_NOMINA}" FechaTimbrado="2026-08-15T10:05:00" RfcProvCertifica="SAT970701NN3" SelloCFD="x" NoCertificadoSAT="1" SelloSAT="x"/>
  </cfdi:Complemento>
</cfdi:Comprobante>"""


def test_parser_impuestos_por_tasa_relacionados_y_locales():
    x = parse_cfdi_xml(XML_MIXTO)

    def buscar(naturaleza, impuesto, tasa=None, factor=None):
        return [
            i
            for i in x.impuestos
            if i.naturaleza == naturaleza
            and i.impuesto == impuesto
            and (tasa is None or i.tasa == Decimal(tasa))
            and (factor is None or i.tipo_factor == factor)
            and not i.nombre_local
        ]

    iva16 = buscar("traslado", "002", "0.160000")[0]
    assert iva16.base == Decimal("5000.00") and iva16.importe == Decimal("800.00")
    iva8 = buscar("traslado", "002", "0.080000")[0]
    assert iva8.base == Decimal("3090.00") and iva8.importe == Decimal("247.20")
    exento = buscar("traslado", "002", factor="Exento")[0]
    assert exento.base == Decimal("1500.00") and exento.importe == Decimal("0")
    ieps = buscar("traslado", "003", "0.030000")[0]
    assert ieps.importe == Decimal("90.00")
    assert buscar("retencion", "001")[0].importe == Decimal("500.00")

    no_objeto = [i for i in x.impuestos if i.naturaleza == "no_objeto"][0]
    assert no_objeto.base == Decimal("1000.00")

    local = [i for i in x.impuestos if i.nombre_local][0]
    assert local.nombre_local == "ISH" and local.importe == Decimal("105.00")

    assert [(r.tipo_relacion, r.uuid) for r in x.relacionados] == [("04", UUID_RELACIONADA)]
    assert x.complementos == ["ImpuestosLocales"]
    assert x.pac_rfc == "SAT970701NN3"
    assert x.cuenta_predial == "1234567890"
    assert x.condiciones_pago == "30 dias"
    assert x.lugar_expedicion == "07780" and x.exportacion == "01"


def test_parser_cfdi_global():
    x = parse_cfdi_xml(XML_GLOBAL)
    assert (x.global_periodicidad, x.global_meses, x.global_anio) == ("04", "08", "2026")


def test_parser_complemento_de_nomina():
    x = parse_cfdi_xml(XML_NOMINA)
    n = x.nomina
    assert n is not None
    assert n.version == "1.2" and n.tipo_nomina == "O"
    assert n.total_percepciones == Decimal("12000.00") and n.total_deducciones == Decimal("2000.00")
    assert n.total_otros_pagos == Decimal("150.00")
    assert n.num_dias_pagados == Decimal("15")
    assert n.registro_patronal == "B5510768108"
    assert n.curp_receptor == "PEPJ800101HDFRRN09" and n.num_seguridad_social == "12345678901"
    assert n.puesto == "Analista" and n.departamento == "Operaciones" and n.num_empleado == "0042"
    assert n.antiguedad == "P5Y" and n.periodicidad_pago == "04" and n.clave_ent_fed == "DIF"
    assert n.salario_diario_integrado == Decimal("420.00")
    assert x.complementos == ["Nomina"]

    grupos = {c.grupo for c in n.conceptos}
    assert grupos == {"percepcion", "deduccion", "otro_pago"}
    sueldo = next(c for c in n.conceptos if c.clave == "P001")
    assert sueldo.gravado == Decimal("11000.00") and sueldo.exento == Decimal("1000.00")
    isr = next(c for c in n.conceptos if c.clave == "D002")
    assert isr.concepto == "ISR" and isr.gravado == Decimal("1500.00")


def _setup(client, db, seed_rbac):
    usuario = crear_usuario(db)
    empresa = crear_empresa(db, rfc=EMPRESA)
    agregar_membresia(db, usuario=usuario, empresa=empresa, rol=seed_rbac["administrador"])
    headers = auth_headers(client, email=usuario.email, password="Demo1234!", empresa_id=empresa.id)
    return headers, empresa


def test_carga_guarda_impuestos_relacionados_y_nomina(client, seed_rbac, db):
    headers, empresa = _setup(client, db, seed_rbac)
    archivos = [
        ("mixto.xml", XML_MIXTO.encode()),
        ("global.xml", XML_GLOBAL.encode()),
        ("nomina.xml", XML_NOMINA.encode()),
    ]
    res = client.post(
        "/api/v1/sat/cargar-xml",
        headers=headers,
        files=[("archivos", (nombre, contenido, "text/xml")) for nombre, contenido in archivos],
    )
    assert res.status_code == 200, res.text
    assert res.json()["nuevos"] == 3

    mixto = db.query(Cfdi).filter_by(empresa_id=empresa.id, uuid_fiscal=UUID_MIXTO).one()
    # IVA 16, IVA 8, IVA exento, IEPS 3, retención de ISR, base no objeto y el local ISH.
    assert len(mixto.impuestos) == 7
    assert {r.uuid_relacionado for r in mixto.relacionados} == {UUID_RELACIONADA}
    assert mixto.pac_rfc == "SAT970701NN3" and mixto.cuenta_predial == "1234567890"
    assert mixto.complementos == "ImpuestosLocales"
    assert mixto.moneda == "MXN" and mixto.regimen_receptor == "601"

    glob = db.query(Cfdi).filter_by(empresa_id=empresa.id, uuid_fiscal=UUID_GLOBAL).one()
    assert (glob.global_periodicidad, glob.global_meses, glob.global_anio) == ("04", "08", "2026")

    nom = db.query(Cfdi).filter_by(empresa_id=empresa.id, uuid_fiscal=UUID_NOMINA).one()
    assert nom.tipo == "nomina" and nom.nomina is not None
    assert nom.nomina.puesto == "Analista"
    assert len(nom.nomina.conceptos) == 4
    assert nom.descuento == Decimal("2000.00")


def _cargar(client, headers, archivos):
    res = client.post(
        "/api/v1/sat/cargar-xml",
        headers=headers,
        files=[("archivos", (n, c, "text/xml")) for n, c in archivos],
    )
    assert res.status_code == 200, res.text
    return res.json()


def _fila(client, headers, formato, uuid_fiscal):
    b = client.get(f"/api/v1/cfdi/reporte/{formato}?uuid_fiscal={uuid_fiscal}", headers=headers).json()
    assert len(b["filas"]) >= 1, b
    return dict(zip(b["columnas"], b["filas"][0])), b


def test_reporte_general_ya_no_deja_vacias_las_columnas_del_xml(client, seed_rbac, db):
    headers, _ = _setup(client, db, seed_rbac)
    _cargar(client, headers, [("mixto.xml", XML_MIXTO.encode()), ("global.xml", XML_GLOBAL.encode())])

    fila, b = _fila(client, headers, "general", UUID_MIXTO)
    assert fila["UUIDs relacionados"] == UUID_RELACIONADA
    assert fila["Tipo relacion"] == "04"
    assert fila["pacCertifico"] == "SAT970701NN3"
    assert fila["Cuenta Predial"] == "1234567890"
    assert fila["Complementos"] == "ImpuestosLocales"
    assert fila["Condiciones de pago"] == "30 dias"
    assert fila["IVA Exento"] == 1500.0
    assert fila["No Objeto"] == 1000.0
    assert fila["IEPS Trasladado"] == 90.0
    assert fila["ISR Retenido"] == 500.0
    assert fila["Local trasladado"] == 105.0
    assert fila["Moneda"] == "MXN" and fila["Tipo de cambio"] == 1.0

    # Solo quedan sin dato las que de verdad no están en el XML que recibimos.
    assert set(b["sin_dato"]) == {"Efecto", "SubTotalCombustibles", "IEPS Trasladado No Desglosado", "TotalCombustibles"}

    fila_global, _ = _fila(client, headers, "general", UUID_GLOBAL)
    assert (fila_global["Global periodicidad"], fila_global["Global meses"], fila_global["Global año"]) == ("04", "08", "2026")


def test_reporte_comp_desglosa_cada_tasa(client, seed_rbac, db):
    headers, _ = _setup(client, db, seed_rbac)
    _cargar(client, headers, [("mixto.xml", XML_MIXTO.encode())])

    fila, _ = _fila(client, headers, "comp", UUID_MIXTO)
    assert fila["IVA 16 Base"] == 5000.0 and fila["IVA 16 Importe"] == 800.0
    assert fila["IVA 8 Base"] == 3090.0 and fila["IVA 8 Importe"] == 247.2
    assert fila["IVA Exento Base"] == 1500.0
    assert fila["No Objeto Base"] == 1000.0
    assert fila["IEPS 3 Base"] == 3000.0 and fila["IEPS 3 Importe"] == 90.0
    assert fila["Ret ISR Importe"] == 500.0
    assert fila["Local trasladado"] == 105.0
    # El desglose sustituye a las columnas agregadas del general.
    assert "IVA Trasladado 16%" not in fila


def test_reporte_de_nomina_y_sus_conceptos(client, seed_rbac, db):
    headers, _ = _setup(client, db, seed_rbac)
    _cargar(client, headers, [("nomina.xml", XML_NOMINA.encode()), ("mixto.xml", XML_MIXTO.encode())])

    fila, b = _fila(client, headers, "nomina", UUID_NOMINA)
    assert len(b["filas"]) == 1  # la factura no se cuela en el reporte de nómina
    assert fila["NumEmpleado"] == "0042" and fila["Puesto"] == "Analista"
    assert fila["RegistroPatronal"] == "B5510768108"
    assert fila["ReceptorCurp"] == "PEPJ800101HDFRRN09"
    assert fila["TotalPercepciones"] == 12000.0 and fila["TotalDeducciones"] == 2000.0
    assert fila["TotalOtrosPagos"] == 150.0
    assert fila["FechaPago"] == "2026-08-15" and fila["NumDiasPagados"] == 15.0
    assert fila["SalarioDiarioIntegrado"] == 420.0

    b = client.get(f"/api/v1/cfdi/reporte/nomina_conceptos?uuid_fiscal={UUID_NOMINA}", headers=headers).json()
    filas = [dict(zip(b["columnas"], f)) for f in b["filas"]]
    assert len(filas) == 4  # 1 percepción + 2 deducciones + 1 otro pago
    sueldo = next(f for f in filas if f["Clave"] == "P001")
    assert sueldo["Grupo"] == "PERCEPCION" and sueldo["Gravado"] == 11000.0 and sueldo["Exento"] == 1000.0
    assert sueldo["Importe"] == 12000.0
    assert {f["Grupo"] for f in filas} == {"PERCEPCION", "DEDUCCION", "OTRO PAGO"}


def test_reporte_de_conciliacion(client, seed_rbac, db):
    headers, _ = _setup(client, db, seed_rbac)
    _cargar(client, headers, [("mixto.xml", XML_MIXTO.encode())])

    fila, _ = _fila(client, headers, "conciliacion", UUID_MIXTO)
    # PUE: se considera cobrada al emitirse, así que concilia completa.
    assert fila["EstadoPago"] == "COBRADO"
    assert fila["Importe pagado"] == 11294.0
    assert fila["Saldo Insoluto"] == 0.0
    assert fila["Resultado conciliacion"] == "CONCILIADO"
    assert fila["IVA 16%"] == 800.0 and fila["IVA Exento"] == 1500.0
    assert fila["Estado SAT"] == "VIGENTE"
