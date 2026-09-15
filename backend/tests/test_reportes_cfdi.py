"""Reportes de CFDI con el layout de los despachos (ONEFACTURE / MiAdminPro).

El formato `general` debe salir columna por columna como la hoja INGRESOS/GASTOS
de los papeles de trabajo del contador, con las columnas manuales ya resueltas.
"""

from datetime import date

from app.modules.cfdi.models import Cfdi, CfdiPagoDocto
from app.modules.sat.mock_generator import generar_cfdis_mock
from tests.conftest import agregar_membresia, auth_headers, crear_empresa, crear_usuario

# Primeras columnas del reporte GENERAL, tal cual las entrega el portal.
INICIO_GENERAL = [
    "Periodo",
    "Version",
    "UUID",
    "UUIDs relacionados",
    "Tipo relacion",
    "CP Expedicion",
    "Serie",
    "Folio",
    "Tipo",
    "Fecha emision",
    "Fecha certificacion",
    "pacCertifico",
    "Regimen emisor",
    "RFC emisor",
    "Razon emisor",
    "RFC receptor",
    "Razon receptor",
    "Regimen receptor",
    "Domicilio receptor",
    "Claves de productos",
    "Conceptos",
]
COLUMNAS_MANUALES = ["TIPO DE DEDUCCION", "CONCEPTO", "CUENTA CONTABLE", "PAG/PEN", "REF BANCARIA", "COMPLEMENTO PAGO", "FECHA PAGO", "MES PAGO"]


def _setup(client, db, seed_rbac, cantidad=60):
    usuario = crear_usuario(db)
    empresa = crear_empresa(db, rfc="LORM850312MN1")
    agregar_membresia(db, usuario=usuario, empresa=empresa, rol=seed_rbac["administrador"])
    generar_cfdis_mock(db, empresa=empresa, cantidad=cantidad, dias_atras=120, seed=5)
    headers = auth_headers(client, email=usuario.email, password="Demo1234!", empresa_id=empresa.id)
    return headers, empresa


def test_reporte_general_respeta_el_layout_del_despacho(client, seed_rbac, db):
    headers, empresa = _setup(client, db, seed_rbac)
    res = client.get("/api/v1/cfdi/reporte/general?tipo=egreso", headers=headers)
    assert res.status_code == 200, res.text
    b = res.json()

    assert b["columnas"][: len(INICIO_GENERAL)] == INICIO_GENERAL
    assert b["columnas"][-len(COLUMNAS_MANUALES) :] == COLUMNAS_MANUALES
    assert b["columnas"].index("SubTotal") < b["columnas"].index("Total")
    assert len(b["columnas"]) == 63  # 55 del portal + 8 del papel de trabajo
    assert all(len(f) == len(b["columnas"]) for f in b["filas"])
    assert b["truncado"] is False

    # Las columnas que todavía no tenemos se declaran, no se esconden.
    assert "SubTotalCombustibles" in b["sin_dato"] and "TotalCombustibles" in b["sin_dato"]
    assert "UUID" not in b["sin_dato"] and "SubTotal" not in b["sin_dato"]

    # Cubre TODOS los gastos, no solo una página.
    gastos = db.query(Cfdi).filter_by(empresa_id=empresa.id, tipo="egreso").count()
    assert b["total"] == gastos == len(b["filas"])


def test_reporte_trae_resueltas_las_columnas_manuales(client, seed_rbac, db):
    headers, empresa = _setup(client, db, seed_rbac)
    gasto = (
        db.query(Cfdi)
        .filter_by(empresa_id=empresa.id, tipo="egreso", metodo_pago_codigo="PUE", estatus="vigente")
        .order_by(Cfdi.fecha)
        .first()
    )
    client.put(
        f"/api/v1/cfdi/{gasto.id}/clasificacion",
        headers=headers,
        json={"clasificacion": "no_deducible", "concepto": "Comisiones bancarias", "cuenta_contable": "6100-055-000", "referencia_bancaria": "ENE 1002"},
    )

    b = client.get(f"/api/v1/cfdi/reporte/general?uuid_fiscal={gasto.uuid_fiscal}", headers=headers).json()
    assert len(b["filas"]) == 1
    fila = dict(zip(b["columnas"], b["filas"][0]))
    assert fila["UUID"] == gasto.uuid_fiscal
    assert fila["TIPO DE DEDUCCION"] == "NO DEDUCIBLE"
    assert fila["CONCEPTO"] == "Comisiones bancarias"
    assert fila["CUENTA CONTABLE"] == "6100-055-000"
    assert fila["REF BANCARIA"] == "ENE 1002"
    # Una PUE se paga al emitirse: el mes de pago es el de la factura.
    assert fila["PAG/PEN"] == "PAGADO"
    assert fila["FECHA PAGO"] == gasto.fecha.isoformat()
    assert fila["MES PAGO"] == gasto.fecha.month
    assert fila["SubTotal"] == float(gasto.subtotal) and fila["Total"] == float(gasto.total)


def test_ppd_pendiente_y_liquidada_por_rep(client, seed_rbac, db):
    headers, empresa = _setup(client, db, seed_rbac)
    ppd = (
        db.query(Cfdi)
        .filter_by(empresa_id=empresa.id, tipo="egreso", metodo_pago_codigo="PPD", estatus="vigente")
        .order_by(Cfdi.fecha)
        .first()
    )

    def fila_de(uuid_fiscal):
        b = client.get(f"/api/v1/cfdi/reporte/general?uuid_fiscal={uuid_fiscal}", headers=headers).json()
        return dict(zip(b["columnas"], b["filas"][0]))

    fila = fila_de(ppd.uuid_fiscal)
    assert fila["PAG/PEN"] == "PENDIENTE" and fila["FECHA PAGO"] == "" and fila["COMPLEMENTO PAGO"] == ""

    rep = db.query(Cfdi).filter_by(empresa_id=empresa.id, tipo="pago", direccion="recibido").first()
    pagado_el = date(ppd.fecha.year, ppd.fecha.month, 28)
    db.add(
        CfdiPagoDocto(
            cfdi_pago_id=rep.id,
            uuid_relacionado=ppd.uuid_fiscal,
            imp_pagado=ppd.total,
            iva_pagado=ppd.iva,
            fecha_pago=pagado_el,
        )
    )
    db.commit()

    fila = fila_de(ppd.uuid_fiscal)
    assert fila["PAG/PEN"] == "PAGADO"
    assert fila["FECHA PAGO"] == pagado_el.isoformat()
    assert fila["MES PAGO"] == pagado_el.month
    assert fila["COMPLEMENTO PAGO"] == rep.uuid_fiscal


def test_reporte_de_pagos_expande_por_documento(client, seed_rbac, db):
    headers, empresa = _setup(client, db, seed_rbac)
    rep = db.query(Cfdi).filter_by(empresa_id=empresa.id, tipo="pago").first()
    facturas = db.query(Cfdi).filter_by(empresa_id=empresa.id, tipo="egreso").limit(2).all()
    for i, f in enumerate(facturas, start=1):
        db.add(
            CfdiPagoDocto(
                cfdi_pago_id=rep.id,
                uuid_relacionado=f.uuid_fiscal,
                num_parcialidad=i,
                imp_pagado=f.total,
                iva_pagado=f.iva,
                fecha_pago=rep.fecha,
            )
        )
    db.commit()

    b = client.get(f"/api/v1/cfdi/reporte/pagos?uuid_fiscal={rep.uuid_fiscal}", headers=headers).json()
    assert "UUID documento" in b["columnas"] and "Num parcialidad" in b["columnas"]
    # Un REP con dos documentos liquidados da dos filas.
    assert len(b["filas"]) == 2
    doctos = {dict(zip(b["columnas"], f))["UUID documento"] for f in b["filas"]}
    assert doctos == {f.uuid_fiscal for f in facturas}


def test_formato_desconocido_y_permisos(client, seed_rbac, db):
    headers, _ = _setup(client, db, seed_rbac, cantidad=10)
    assert client.get("/api/v1/cfdi/reporte/inventado", headers=headers).status_code == 404
    assert client.get("/api/v1/cfdi/reporte/general", headers={}).status_code == 401


def test_reportes_por_tipo_no_gastan_el_tope_en_cfdi_ajenos(client, seed_rbac, db, monkeypatch):
    """El tipo se fuerza en la consulta: si se filtrara al armar las filas, con
    muchos CFDI el tope se gastaría en facturas y se perderían recibos."""
    from app.modules.cfdi import crud as cfdi_crud

    headers, empresa = _setup(client, db, seed_rbac, cantidad=80)
    nominas = db.query(Cfdi).filter_by(empresa_id=empresa.id, tipo="nomina").count()
    assert nominas > 0

    # Con un tope diminuto, el reporte de nómina sigue trayendo los recibos.
    monkeypatch.setattr(cfdi_crud, "TOPE_REPORTE", 5)
    b = client.get("/api/v1/cfdi/reporte/nomina", headers=headers).json()
    assert b["total"] == nominas
    assert len(b["filas"]) == min(nominas, 5)
    assert b["truncado"] is (nominas > 5)


def test_clasificacion_masiva_no_cuenta_dos_veces_el_mismo_id(client, seed_rbac, db):
    headers, empresa = _setup(client, db, seed_rbac, cantidad=20)
    gasto = db.query(Cfdi).filter_by(empresa_id=empresa.id, tipo="egreso").first()
    res = client.post(
        "/api/v1/cfdi/clasificacion-masiva",
        headers=headers,
        json={"cfdi_ids": [str(gasto.id), str(gasto.id)], "concepto": "PEAJE"},
    )
    assert res.json() == {"actualizados": 1, "omitidos": 0}


def test_nomina_exige_su_propio_permiso(client, seed_rbac, db):
    """Ver CFDI no debe alcanzar para bajar sueldos, CURP, NSS y cuentas bancarias."""
    from app.modules.auth.models import Rol

    sin_nomina = Rol(
        nombre="auxiliar",
        permisos=[seed_rbac["permisos"][c] for c in ("empresas.leer", "cfdi.leer")],
    )
    db.add(sin_nomina)
    db.commit()

    usuario = crear_usuario(db)
    empresa = crear_empresa(db, rfc="LORM850312MN1")
    agregar_membresia(db, usuario=usuario, empresa=empresa, rol=sin_nomina)
    generar_cfdis_mock(db, empresa=empresa, cantidad=20, dias_atras=60, seed=9)
    headers = auth_headers(client, email=usuario.email, password="Demo1234!", empresa_id=empresa.id)

    assert client.get("/api/v1/cfdi/reporte/general", headers=headers).status_code == 200
    assert client.get("/api/v1/cfdi/reporte/nomina", headers=headers).status_code == 403
    assert client.get("/api/v1/cfdi/reporte/nomina_conceptos", headers=headers).status_code == 403
