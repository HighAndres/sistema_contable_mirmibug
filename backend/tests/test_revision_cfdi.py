"""Revisión del módulo CFDI (notas del equipo, octubre 2026): desglose de IVA,
estatus de conciliación bancaria en la lista, "se considera para la declaración",
filtro por uso de CFDI, columnas/filtros de nómina y campos del REP."""

import uuid
from datetime import date
from decimal import Decimal

from app.modules.cfdi.models import Cfdi, CfdiImpuesto, CfdiNomina, CfdiNominaConcepto, CfdiPagoDocto
from app.modules.conciliacion.models import CuentaBancaria, LigaConciliacion, MovimientoBancario
from app.modules.auth.models import Rol
from tests.conftest import agregar_membresia, auth_headers, crear_empresa, crear_usuario


def _setup(client, db, seed_rbac):
    usuario = crear_usuario(db)
    empresa = crear_empresa(db, rfc="LORM850312MN1")
    agregar_membresia(db, usuario=usuario, empresa=empresa, rol=seed_rbac["administrador"])
    headers = auth_headers(client, email=usuario.email, password="Demo1234!", empresa_id=empresa.id)
    return headers, empresa


def _cfdi(db, empresa, *, tipo="egreso", direccion="recibido", total="1160.00", iva="160.00", subtotal="1000.00", **kw):
    c = Cfdi(
        empresa_id=empresa.id,
        uuid_fiscal=str(uuid.uuid4()).upper(),
        tipo=tipo,
        direccion=direccion,
        rfc_emisor="AAA010101AAA",
        nombre_emisor="Proveedor SA",
        rfc_receptor=empresa.rfc,
        nombre_receptor=empresa.razon_social,
        subtotal=Decimal(subtotal),
        iva=Decimal(iva),
        total=Decimal(total),
        fecha=kw.pop("fecha", date(2026, 3, 10)),
        **kw,
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def _liga(db, empresa, cfdi, importe, *, fecha=date(2026, 3, 12)):
    cuenta = db.query(CuentaBancaria).filter_by(empresa_id=empresa.id).first()
    if cuenta is None:
        cuenta = CuentaBancaria(empresa_id=empresa.id, banco="BBVA", alias="Principal")
        db.add(cuenta)
        db.flush()
    mov = MovimientoBancario(
        empresa_id=empresa.id,
        cuenta_id=cuenta.id,
        fecha=fecha,
        concepto="PAGO PROVEEDOR",
        cargo=Decimal(importe),
        abono=0,
        huella=uuid.uuid4().hex[:40],
        estado="conciliado",
    )
    db.add(mov)
    db.flush()
    db.add(LigaConciliacion(movimiento_id=mov.id, cfdi_id=cfdi.id, importe=Decimal(importe)))
    db.commit()


def _item(client, headers, cfdi):
    b = client.get(f"/api/v1/cfdi?uuid_fiscal={cfdi.uuid_fiscal}", headers=headers).json()
    assert b["total"] == 1, b
    return b["items"][0]


def test_desglose_iva_por_tasa_en_la_lista(client, seed_rbac, db):
    headers, empresa = _setup(client, db, seed_rbac)
    c = _cfdi(db, empresa, metodo_pago_codigo="PUE", uso_cfdi_codigo="G03")
    db.add_all(
        [
            CfdiImpuesto(cfdi_id=c.id, naturaleza="traslado", impuesto="002", tipo_factor="Tasa", tasa=Decimal("0.16"), base=Decimal("800"), importe=Decimal("128")),
            CfdiImpuesto(cfdi_id=c.id, naturaleza="traslado", impuesto="002", tipo_factor="Exento", base=Decimal("200"), importe=Decimal("0")),
            # Una retención de ISR no es IVA trasladado: no debe salir en el desglose.
            CfdiImpuesto(cfdi_id=c.id, naturaleza="retencion", impuesto="001", tipo_factor="Tasa", tasa=Decimal("0.10"), base=Decimal("1000"), importe=Decimal("100")),
        ]
    )
    db.commit()
    item = _item(client, headers, c)
    desglose = {f["etiqueta"]: f for f in item["desglose_iva"]}
    assert set(desglose) == {"16%", "Exento"}
    assert desglose["16%"]["base"] == 800 and desglose["16%"]["importe"] == 128
    assert desglose["Exento"]["base"] == 200

    detalle = client.get(f"/api/v1/cfdi/{c.id}", headers=headers).json()
    assert len(detalle["impuestos"]) == 3  # el desglose completo sí trae la retención


def test_estatus_conciliado_y_en_declaracion(client, seed_rbac, db):
    headers, empresa = _setup(client, db, seed_rbac)
    # PUE deducible sin conciliar: pagada (cuenta para la declaración) pero sin liga.
    pue = _cfdi(db, empresa, metodo_pago_codigo="PUE")
    item = _item(client, headers, pue)
    assert item["conciliado"] is None and item["en_declaracion"] is True

    # PPD sin REP ni pago manual: pendiente, fuera de la declaración…
    ppd = _cfdi(db, empresa, metodo_pago_codigo="PPD")
    assert _item(client, headers, ppd)["en_declaracion"] is False
    # …hasta que la conciliación bancaria la cubre por completo.
    _liga(db, empresa, ppd, "500.00")
    item = _item(client, headers, ppd)
    assert item["conciliado"] == "parcial" and item["en_declaracion"] is False
    _liga(db, empresa, ppd, "660.00")
    item = _item(client, headers, ppd)
    assert item["conciliado"] == "conciliado" and item["conciliado_importe"] == 1160
    assert item["en_declaracion"] is True

    # Marcada no deducible: el contador la saca a mano aunque esté conciliada.
    client.put(f"/api/v1/cfdi/{ppd.id}/clasificacion", headers=headers, json={"clasificacion": "no_deducible"})
    assert _item(client, headers, ppd)["en_declaracion"] is False

    # El detalle trae los movimientos bancarios ligados.
    detalle = client.get(f"/api/v1/cfdi/{ppd.id}", headers=headers).json()
    assert len(detalle["ligas_bancarias"]) == 2
    assert detalle["ligas_bancarias"][0]["cuenta"] == "Principal"


def test_filtro_por_uso_cfdi_y_valores(client, seed_rbac, db):
    headers, empresa = _setup(client, db, seed_rbac)
    _cfdi(db, empresa, uso_cfdi_codigo="G03", metodo_pago_codigo="PUE")
    _cfdi(db, empresa, uso_cfdi_codigo="I04", metodo_pago_codigo="PUE")
    assert client.get("/api/v1/cfdi?uso_cfdi=G03", headers=headers).json()["total"] == 1

    valores = client.get("/api/v1/cfdi/filtros/valores", headers=headers).json()
    assert valores["usos_cfdi"] == ["G03", "I04"]


def _nomina(db, empresa, *, entidad="JAL", registro="B5510768108", periodicidad="04", fecha_pago=date(2026, 3, 15), total="8000.00"):
    c = _cfdi(
        db,
        empresa,
        tipo="nomina",
        direccion="emitido",
        subtotal=total,
        iva="0.00",
        total=total,
        fecha=date(2026, 3, 14),
    )
    n = CfdiNomina(
        cfdi_id=c.id,
        tipo_nomina="O",
        fecha_pago=fecha_pago,
        fecha_inicial_pago=date(2026, 3, 1),
        fecha_final_pago=date(2026, 3, 15),
        num_dias_pagados=Decimal("15"),
        total_percepciones=Decimal(total),
        total_deducciones=Decimal("1200.00"),
        total_otros_pagos=Decimal("100.00"),
        registro_patronal=registro,
        periodicidad_pago=periodicidad,
        clave_ent_fed=entidad,
        curp_receptor="XEXX010101HNEXXXA4",
        num_seguridad_social="12345678901",
    )
    db.add(n)
    db.flush()
    db.add_all(
        [
            CfdiNominaConcepto(nomina_id=n.id, grupo="percepcion", tipo_codigo="001", concepto="Sueldo", gravado=Decimal(total), exento=0),
            CfdiNominaConcepto(nomina_id=n.id, grupo="deduccion", tipo_codigo="002", concepto="ISR", gravado=Decimal("1200.00"), exento=0),
            CfdiNominaConcepto(nomina_id=n.id, grupo="otro_pago", tipo_codigo="002", concepto="Subsidio", gravado=0, exento=Decimal("100.00")),
        ]
    )
    db.commit()
    return c


def test_nomina_columnas_filtros_y_detalle(client, seed_rbac, db):
    headers, empresa = _setup(client, db, seed_rbac)
    recibo = _nomina(db, empresa)
    _nomina(db, empresa, entidad="CMX", registro="OTRO123", periodicidad="05")

    item = _item(client, headers, recibo)
    assert item["nomina_percepciones"] == 8000 and item["nomina_deducciones"] == 1200 and item["nomina_otros_pagos"] == 100
    assert item["registro_patronal"] == "B5510768108" and item["entidad_codigo"] == "JAL" and item["periodicidad_codigo"] == "04"
    assert item["nomina_fecha_pago"] == "2026-03-15"

    # Filtros del listado de nómina.
    assert client.get("/api/v1/cfdi?registro_patronal=B5510768108", headers=headers).json()["total"] == 1
    assert client.get("/api/v1/cfdi?entidad=CMX", headers=headers).json()["total"] == 1
    assert client.get("/api/v1/cfdi?periodicidad=05", headers=headers).json()["total"] == 1

    valores = client.get("/api/v1/cfdi/filtros/valores", headers=headers).json()
    assert valores["registros_patronales"] == ["B5510768108", "OTRO123"]
    assert valores["entidades"] == ["CMX", "JAL"] and valores["periodicidades"] == ["04", "05"]

    # Detalle: desglose de percepciones/deducciones/otros pagos.
    detalle = client.get(f"/api/v1/cfdi/{recibo.id}", headers=headers).json()
    grupos = {cn["grupo"] for cn in detalle["nomina"]["conceptos"]}
    assert grupos == {"percepcion", "deduccion", "otro_pago"}
    # Con nomina.leer (administrador) sí salen los datos personales.
    assert detalle["nomina"]["num_seguridad_social"] == "12345678901"


def test_detalle_nomina_oculta_datos_personales_sin_permiso(client, seed_rbac, db):
    usuario = crear_usuario(db)
    empresa = crear_empresa(db)
    permisos = seed_rbac["permisos"]
    sin_nomina = Rol(nombre="auxiliar", es_sistema=False, permisos=[permisos["cfdi.leer"]])
    db.add(sin_nomina)
    db.commit()
    agregar_membresia(db, usuario=usuario, empresa=empresa, rol=sin_nomina)
    headers = auth_headers(client, email=usuario.email, password="Demo1234!", empresa_id=empresa.id)

    recibo = _nomina(db, empresa)
    detalle = client.get(f"/api/v1/cfdi/{recibo.id}", headers=headers).json()
    # El desglose del recibo sí se ve; CURP/NSS/cuenta bancaria no.
    assert detalle["nomina"]["total_percepciones"] == 8000
    assert len(detalle["nomina"]["conceptos"]) == 3
    assert detalle["nomina"]["num_seguridad_social"] is None
    assert detalle["nomina"]["curp_receptor"] is None


def test_rep_fecha_importes_y_liga_a_facturas(client, seed_rbac, db):
    headers, empresa = _setup(client, db, seed_rbac)
    factura = _cfdi(db, empresa, metodo_pago_codigo="PPD")
    rep = _cfdi(db, empresa, tipo="pago", subtotal="0.00", iva="0.00", total="0.00", fecha=date(2026, 4, 2))
    db.add(
        CfdiPagoDocto(
            cfdi_pago_id=rep.id,
            uuid_relacionado=factura.uuid_fiscal,
            num_parcialidad=1,
            imp_pagado=Decimal("1160.00"),
            imp_saldo_insoluto=Decimal("0.00"),
            iva_pagado=Decimal("160.00"),
            fecha_pago=date(2026, 3, 30),
        )
    )
    db.commit()

    item = _item(client, headers, rep)
    assert item["rep_fecha_pago"] == "2026-03-30"
    assert item["rep_importe_pagado"] == 1160 and item["rep_iva_pagado"] == 160
    assert item["en_declaracion"] is None  # un REP no se marca: va por su propia vía
    assert item["desglose_iva"] == [{"etiqueta": "IVA pagado", "base": 0, "importe": 160}]

    # Del REP se puede ir directo a la factura que liquida.
    detalle = client.get(f"/api/v1/cfdi/{rep.id}", headers=headers).json()
    assert detalle["pagos_relacionados"][0]["cfdi_relacionado_id"] == str(factura.id)

    # Un REP conciliado se compara contra lo que paga (su total es 0).
    _liga(db, empresa, rep, "1160.00", fecha=date(2026, 3, 30))
    assert _item(client, headers, rep)["conciliado"] == "conciliado"


def test_rep_sin_alerta_de_descuadre_de_conceptos(db, seed_rbac, client):
    from app.modules.rules.engine import evaluar_cfdi

    headers, empresa = _setup(client, db, seed_rbac)
    rep = _cfdi(db, empresa, tipo="pago", subtotal="0.00", iva="0.00", total="0.00")
    # Sin conceptos que cuadren: en una factura esto alertaría, en un REP no.
    alertas = evaluar_cfdi(rep)
    assert all(codigo != "descuadre_subtotal" for codigo, _, _ in alertas)
