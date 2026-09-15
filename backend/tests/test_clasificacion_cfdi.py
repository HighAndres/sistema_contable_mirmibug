"""Clasificación manual del CFDI (el papel de trabajo del contador): marcar un
gasto como deducible / no deducible / deducción personal, con concepto, cuenta
contable y referencia bancaria; y que lo no deducible deje de restar en el ISR y
su IVA deje de ser acreditable."""

from datetime import date

from app.modules.auth.models import Rol
from app.modules.cfdi.models import Cfdi, CfdiPagoDocto
from app.modules.sat.mock_generator import generar_cfdis_mock
from tests.conftest import agregar_membresia, auth_headers, crear_empresa, crear_usuario


def _setup(client, db, seed_rbac, rol="administrador"):
    usuario = crear_usuario(db)
    empresa = crear_empresa(db, rfc="LORM850312MN1")  # PF → ISR en flujo
    empresa.regimen_fiscal_codigo = "612"
    db.commit()
    agregar_membresia(db, usuario=usuario, empresa=empresa, rol=seed_rbac[rol])
    generar_cfdis_mock(db, empresa=empresa, cantidad=120, dias_atras=200, seed=11)
    headers = auth_headers(client, email=usuario.email, password="Demo1234!", empresa_id=empresa.id)
    return headers, empresa


def _gasto_pue(db, empresa, anio=None):
    q = db.query(Cfdi).filter_by(empresa_id=empresa.id, tipo="egreso", metodo_pago_codigo="PUE", estatus="vigente")
    gastos = q.order_by(Cfdi.fecha.desc()).all()
    if anio:
        gastos = [g for g in gastos if g.fecha.year == anio]
    return gastos[0]


def test_clasificar_una_factura(client, seed_rbac, db):
    headers, empresa = _setup(client, db, seed_rbac)
    gasto = _gasto_pue(db, empresa)

    res = client.put(
        f"/api/v1/cfdi/{gasto.id}/clasificacion",
        headers=headers,
        json={
            "clasificacion": "deducible",
            "concepto": "  telefonos  ",
            "cuenta_contable": "6100-039-000",
            "referencia_bancaria": "ene 1061",
        },
    )
    assert res.status_code == 200, res.text
    b = res.json()
    # Solo se recortan espacios: las mayúsculas/minúsculas quedan como se capturaron.
    assert b["clasificacion"] == "deducible"
    assert b["concepto"] == "telefonos"
    assert b["cuenta_contable"] == "6100-039-000"
    assert b["referencia_bancaria"] == "ene 1061"

    # Se ve en lista y detalle
    det = client.get(f"/api/v1/cfdi/{gasto.id}", headers=headers).json()
    assert det["concepto"] == "telefonos"

    # Mandar un campo en nulo lo limpia (es la edición de la fila completa)
    res = client.put(f"/api/v1/cfdi/{gasto.id}/clasificacion", headers=headers, json={"clasificacion": "no_deducible"})
    assert res.status_code == 200
    assert res.json()["concepto"] is None and res.json()["cuenta_contable"] is None

    # Clasificación inválida
    assert client.put(f"/api/v1/cfdi/{gasto.id}/clasificacion", headers=headers, json={"clasificacion": "inventada"}).status_code == 422

    # Un REP no se clasifica
    rep = db.query(Cfdi).filter_by(empresa_id=empresa.id, tipo="pago").first()
    if rep is not None:
        res = client.put(f"/api/v1/cfdi/{rep.id}/clasificacion", headers=headers, json={"clasificacion": "deducible"})
        assert res.status_code == 400


def test_filtros_y_valores_de_clasificacion(client, seed_rbac, db):
    headers, empresa = _setup(client, db, seed_rbac)
    gastos = db.query(Cfdi).filter_by(empresa_id=empresa.id, tipo="egreso", estatus="vigente").limit(3).all()

    valores = client.get("/api/v1/cfdi/clasificacion/valores", headers=headers).json()
    sin_clasificar_antes = valores["sin_clasificar"]
    assert sin_clasificar_antes > 0 and valores["conceptos"] == []

    for g, concepto in zip(gastos, ("PEAJE", "MENSAJERIA", "PEAJE")):
        res = client.put(
            f"/api/v1/cfdi/{g.id}/clasificacion",
            headers=headers,
            json={"clasificacion": "deducible", "concepto": concepto, "cuenta_contable": "6100-038-000"},
        )
        assert res.status_code == 200

    valores = client.get("/api/v1/cfdi/clasificacion/valores", headers=headers).json()
    assert valores["conceptos"] == ["MENSAJERIA", "PEAJE"]  # distintos y ordenados
    assert valores["cuentas_contables"] == ["6100-038-000"]
    assert valores["sin_clasificar"] == sin_clasificar_antes - 3

    peajes = client.get("/api/v1/cfdi?concepto=peaje&limit=500", headers=headers).json()
    assert len(peajes["items"]) == 2
    deducibles = client.get("/api/v1/cfdi?clasificacion=deducible&limit=500", headers=headers).json()
    assert len(deducibles["items"]) == 3
    pendientes = client.get("/api/v1/cfdi?clasificacion=sin_clasificar&limit=500", headers=headers).json()
    assert all(c["clasificacion"] is None for c in pendientes["items"])
    assert all(c["tipo"] in ("ingreso", "egreso", "nota_credito") for c in pendientes["items"])


def test_clasificacion_masiva_no_pisa_lo_ya_capturado(client, seed_rbac, db):
    headers, empresa = _setup(client, db, seed_rbac)
    gastos = db.query(Cfdi).filter_by(empresa_id=empresa.id, tipo="egreso", estatus="vigente").limit(4).all()
    ids = [str(g.id) for g in gastos]

    client.put(f"/api/v1/cfdi/{ids[0]}/clasificacion", headers=headers, json={"clasificacion": "deducible", "cuenta_contable": "6100-001-000"})

    res = client.post(
        "/api/v1/cfdi/clasificacion-masiva",
        headers=headers,
        json={"cfdi_ids": ids, "clasificacion": "deducible", "concepto": "peaje"},
    )
    assert res.status_code == 200, res.text
    assert res.json() == {"actualizados": 4, "omitidos": 0}

    # El concepto se aplicó a todos y la cuenta del primero NO se borró.
    primero = client.get(f"/api/v1/cfdi/{ids[0]}", headers=headers).json()
    assert primero["concepto"] == "peaje" and primero["cuenta_contable"] == "6100-001-000"
    assert client.get(f"/api/v1/cfdi/{ids[3]}", headers=headers).json()["concepto"] == "peaje"

    # Sin campos que aplicar → 400
    assert client.post("/api/v1/cfdi/clasificacion-masiva", headers=headers, json={"cfdi_ids": ids}).status_code == 400

    # Un REP en la lista se omite, no rompe el lote.
    rep = db.query(Cfdi).filter_by(empresa_id=empresa.id, tipo="pago").first()
    if rep is not None:
        res = client.post(
            "/api/v1/cfdi/clasificacion-masiva",
            headers=headers,
            json={"cfdi_ids": [str(rep.id), ids[0]], "concepto": "OTRO"},
        )
        assert res.json() == {"actualizados": 1, "omitidos": 1}


def test_no_deducible_sale_del_isr_y_del_iva_acreditable(client, seed_rbac, db):
    headers, empresa = _setup(client, db, seed_rbac)
    anio = date.today().year
    gasto = _gasto_pue(db, empresa, anio=anio)
    mes = gasto.fecha.month

    iva_antes = client.get(f"/api/v1/impuestos/iva?anio={anio}&mes={mes}", headers=headers).json()
    isr_antes = client.get(f"/api/v1/impuestos/isr?anio={anio}", headers=headers).json()
    ded_antes = next(m for m in isr_antes["meses"] if m["mes"] == mes)["deducciones_mes"]

    res = client.put(
        f"/api/v1/cfdi/{gasto.id}/clasificacion",
        headers=headers,
        json={"clasificacion": "no_deducible", "concepto": "NO DEDUCIBLES"},
    )
    assert res.status_code == 200

    # IVA: baja el acreditable exactamente el IVA del gasto y aparece en su fila.
    iva = client.get(f"/api/v1/impuestos/iva?anio={anio}&mes={mes}", headers=headers).json()
    assert round(iva_antes["acreditable_pagado"] - iva["acreditable_pagado"], 2) == float(gasto.iva)
    fila = next(f for f in iva["recibidas"] if f["concepto"] == "No deducibles")
    assert fila["num_cfdis"] == 1 and fila["iva"] == float(gasto.iva)

    # ISR: la deducción del mes baja exactamente el subtotal del gasto.
    isr = client.get(f"/api/v1/impuestos/isr?anio={anio}", headers=headers).json()
    ded = next(m for m in isr["meses"] if m["mes"] == mes)["deducciones_mes"]
    assert round(ded_antes - ded, 2) == float(gasto.subtotal)

    # Una deducción personal tampoco resta en el provisional.
    client.put(f"/api/v1/cfdi/{gasto.id}/clasificacion", headers=headers, json={"clasificacion": "deduccion_personal"})
    isr = client.get(f"/api/v1/impuestos/isr?anio={anio}", headers=headers).json()
    assert next(m for m in isr["meses"] if m["mes"] == mes)["deducciones_mes"] == ded

    # Volver a deducible restaura las cifras.
    client.put(f"/api/v1/cfdi/{gasto.id}/clasificacion", headers=headers, json={"clasificacion": "deducible"})
    isr = client.get(f"/api/v1/impuestos/isr?anio={anio}", headers=headers).json()
    assert next(m for m in isr["meses"] if m["mes"] == mes)["deducciones_mes"] == ded_antes


def test_clasificar_requiere_permiso_de_edicion(client, seed_rbac, db):
    """Con cfdi.leer se consulta la clasificación, pero capturarla pide cfdi.editar."""
    solo_lectura = Rol(nombre="consulta", permisos=[seed_rbac["permisos"]["cfdi.leer"]])
    db.add(solo_lectura)
    db.commit()

    usuario = crear_usuario(db)
    empresa = crear_empresa(db, rfc="LORM850312MN1")
    agregar_membresia(db, usuario=usuario, empresa=empresa, rol=solo_lectura)
    generar_cfdis_mock(db, empresa=empresa, cantidad=20, dias_atras=60, seed=3)
    headers = auth_headers(client, email=usuario.email, password="Demo1234!", empresa_id=empresa.id)
    gasto = _gasto_pue(db, empresa)

    assert client.get("/api/v1/cfdi/clasificacion/valores", headers=headers).status_code == 200
    res = client.put(f"/api/v1/cfdi/{gasto.id}/clasificacion", headers=headers, json={"clasificacion": "deducible"})
    assert res.status_code == 403
    assert client.post("/api/v1/cfdi/clasificacion-masiva", headers=headers, json={"cfdi_ids": [str(gasto.id)], "concepto": "X"}).status_code == 403


def test_rep_que_liquida_una_factura_no_deducible_tampoco_acredita(client, seed_rbac, db):
    """Un REP no se clasifica: hereda el efecto de la factura PPD que liquida."""
    headers, empresa = _setup(client, db, seed_rbac)
    anio = date.today().year
    ppd = (
        db.query(Cfdi)
        .filter_by(empresa_id=empresa.id, tipo="egreso", metodo_pago_codigo="PPD", estatus="vigente")
        .order_by(Cfdi.fecha.desc())
        .first()
    )
    rep = (
        db.query(Cfdi)
        .filter_by(empresa_id=empresa.id, tipo="pago", direccion="recibido", estatus="vigente")
        .order_by(Cfdi.fecha.desc())
        .first()
    )
    assert ppd is not None and rep is not None
    rep.fecha = ppd.fecha
    db.add(
        CfdiPagoDocto(
            cfdi_pago_id=rep.id,
            uuid_relacionado=ppd.uuid_fiscal,
            imp_pagado=ppd.total,
            iva_pagado=ppd.iva,
            fecha_pago=rep.fecha,
        )
    )
    db.commit()
    mes = rep.fecha.month

    iva_antes = client.get(f"/api/v1/impuestos/iva?anio={anio}&mes={mes}", headers=headers).json()
    isr_antes = client.get(f"/api/v1/impuestos/isr?anio={anio}", headers=headers).json()
    ded_antes = next(m for m in isr_antes["meses"] if m["mes"] == mes)["deducciones_mes"]

    assert client.put(f"/api/v1/cfdi/{ppd.id}/clasificacion", headers=headers, json={"clasificacion": "no_deducible"}).status_code == 200

    iva = client.get(f"/api/v1/impuestos/iva?anio={anio}&mes={mes}", headers=headers).json()
    # El REP deja de acreditar (y la PPD ya no estaba acreditando: estaba pendiente).
    assert round(iva_antes["acreditable_pagado"] - iva["acreditable_pagado"], 2) == float(rep.iva)
    assert {f["concepto"] for f in iva["recibidas"] if f["num_cfdis"] > 0} >= {"No deducibles"}

    isr = client.get(f"/api/v1/impuestos/isr?anio={anio}", headers=headers).json()
    ded = next(m for m in isr["meses"] if m["mes"] == mes)["deducciones_mes"]
    assert round(ded_antes - ded, 2) == float(rep.subtotal)
