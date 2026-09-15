"""Marcar a mano una factura PPD como pagada/cobrada (sin REP ni movimiento
bancario) y que eso se refleje en lista/detalle, IVA base flujo, ISR en flujo,
saldos de terceros y cuentas por cobrar del dashboard."""

from datetime import date, timedelta
from decimal import Decimal

from app.modules.cfdi.models import Cfdi
from app.modules.sat.mock_generator import generar_cfdis_mock
from tests.conftest import agregar_membresia, auth_headers, crear_empresa, crear_usuario


def _setup(client, db, seed_rbac, rol="administrador"):
    usuario = crear_usuario(db)
    empresa = crear_empresa(db, rfc="LORM850312MN1")  # PF → ISR en flujo
    empresa.regimen_fiscal_codigo = "612"
    db.commit()
    agregar_membresia(db, usuario=usuario, empresa=empresa, rol=seed_rbac[rol])
    generar_cfdis_mock(db, empresa=empresa, cantidad=120, dias_atras=200, seed=7)
    headers = auth_headers(client, email=usuario.email, password="Demo1234!", empresa_id=empresa.id)
    ppd = next(c for c in db.query(Cfdi).filter_by(empresa_id=empresa.id, tipo="ingreso", metodo_pago_codigo="PPD", estatus="vigente").order_by(Cfdi.fecha).all())
    return headers, empresa, ppd


def test_marcar_y_quitar_pago_manual(client, seed_rbac, db):
    headers, empresa, ppd = _setup(client, db, seed_rbac)
    hoy = date.today()
    url = f"/api/v1/cfdi/{ppd.id}/pago-manual"

    # Antes: pendiente en lista y detalle
    det = client.get(f"/api/v1/cfdi/{ppd.id}", headers=headers).json()
    assert det["estado_pago"] == "pendiente" and det["saldo_pendiente"] == det["total"]
    pendientes = client.get("/api/v1/cfdi?tipo=ingreso&estado_pago=pendiente&limit=500", headers=headers).json()
    assert ppd.uuid_fiscal in {c["uuid_fiscal"] for c in pendientes["items"]}
    iva_antes = client.get(f"/api/v1/impuestos/iva?anio={hoy.year}&mes={hoy.month}", headers=headers).json()
    isr_antes = client.get(f"/api/v1/impuestos/isr?anio={hoy.year}", headers=headers).json()
    cxc_antes = client.get(f"/api/v1/reports/dashboard?anio={ppd.fecha.year}&mes={ppd.fecha.month}", headers=headers).json()["cuentas_por_cobrar"]

    # Validaciones
    assert client.post(url, headers=headers, json={"fecha": (ppd.fecha - timedelta(days=1)).isoformat()}).status_code == 400
    pue = db.query(Cfdi).filter_by(empresa_id=empresa.id, tipo="ingreso", metodo_pago_codigo="PUE").first()
    assert client.post(f"/api/v1/cfdi/{pue.id}/pago-manual", headers=headers, json={"fecha": hoy.isoformat()}).status_code == 400

    # Marcar como cobrada hoy
    res = client.post(url, headers=headers, json={"fecha": hoy.isoformat(), "nota": "Depósito sin REP, confirmado con el cliente"})
    assert res.status_code == 200, res.text
    b = res.json()
    assert b["estado_pago"] == "pagada" and b["pago_manual_fecha"] == hoy.isoformat() and "sin REP" in b["pago_manual_nota"]

    det = client.get(f"/api/v1/cfdi/{ppd.id}", headers=headers).json()
    assert det["saldo_pendiente"] == 0 and det["estado_pago"] == "pagada"
    pendientes = client.get("/api/v1/cfdi?tipo=ingreso&estado_pago=pendiente&limit=500", headers=headers).json()
    assert ppd.uuid_fiscal not in {c["uuid_fiscal"] for c in pendientes["items"]}
    pagadas = client.get("/api/v1/cfdi?tipo=ingreso&estado_pago=pagada&limit=500", headers=headers).json()
    assert ppd.uuid_fiscal in {c["uuid_fiscal"] for c in pagadas["items"]}
    assert all(c["metodo_pago_codigo"] == "PUE" or c["estado_pago"] == "pagada" for c in pagadas["items"])

    # IVA del mes del pago manual: el IVA trasladado sube exactamente el IVA de la factura
    iva = client.get(f"/api/v1/impuestos/iva?anio={hoy.year}&mes={hoy.month}", headers=headers).json()
    assert round(iva["trasladado_cobrado"] - iva_antes["trasladado_cobrado"], 2) == float(ppd.iva)
    fila = next(f for f in iva["emitidas"] if f["concepto"] == "Pago manual")
    assert fila["num_cfdis"] == 1 and fila["iva"] == float(ppd.iva)
    # ...y en el año deja de estar en "PPD pendiente"
    anual = client.get(f"/api/v1/impuestos/iva?anio={hoy.year}", headers=headers).json()
    pend_antes = next(f for f in client.get(f"/api/v1/impuestos/iva?anio={hoy.year}", headers=headers).json()["emitidas"] if f["concepto"] == "PPD pendiente")
    assert pend_antes["num_cfdis"] == next(f for f in anual["emitidas"] if f["concepto"] == "PPD pendiente")["num_cfdis"]

    # ISR en flujo (PF): los ingresos del mes del pago suben el subtotal de la factura
    isr = client.get(f"/api/v1/impuestos/isr?anio={hoy.year}", headers=headers).json()
    assert round(isr["meses"][-1]["ingresos_mes"] - isr_antes["meses"][-1]["ingresos_mes"], 2) == float(ppd.subtotal)

    # Cuentas por cobrar del dashboard (mes de la factura) bajan en una factura y su total
    cxc = client.get(f"/api/v1/reports/dashboard?anio={ppd.fecha.year}&mes={ppd.fecha.month}", headers=headers).json()["cuentas_por_cobrar"]
    assert cxc["num_cfdis"] == cxc_antes["num_cfdis"] - 1
    assert round(cxc_antes["total"] - cxc["total"], 2) == float(ppd.total)

    # Bitácora
    entradas = client.get("/api/v1/bitacora?limit=5", headers=headers).json()
    assert any(e["accion"] == "cfdi.pago_manual" for e in entradas)

    # Quitar la marca → vuelve a pendiente y desaparece de "Pago manual"
    res = client.delete(url, headers=headers)
    assert res.status_code == 200 and res.json()["estado_pago"] == "pendiente" and res.json()["pago_manual_fecha"] is None
    assert client.delete(url, headers=headers).status_code == 400
    iva2 = client.get(f"/api/v1/impuestos/iva?anio={hoy.year}&mes={hoy.month}", headers=headers).json()
    assert iva2["trasladado_cobrado"] == iva_antes["trasladado_cobrado"]


def test_pago_manual_requiere_permiso_cfdi_editar(client, seed_rbac, db):
    usuario = crear_usuario(db)
    empresa = crear_empresa(db)
    rol = seed_rbac["contador"]
    rol.permisos = [p for p in rol.permisos if p.codigo != "cfdi.editar"]
    db.commit()
    agregar_membresia(db, usuario=usuario, empresa=empresa, rol=rol)
    generar_cfdis_mock(db, empresa=empresa, cantidad=40, dias_atras=60, seed=5)
    headers = auth_headers(client, email=usuario.email, password="Demo1234!", empresa_id=empresa.id)
    ppd = db.query(Cfdi).filter_by(empresa_id=empresa.id, metodo_pago_codigo="PPD").first()
    res = client.post(f"/api/v1/cfdi/{ppd.id}/pago-manual", headers=headers, json={"fecha": date.today().isoformat()})
    assert res.status_code == 403
    assert Decimal(str(db.get(Cfdi, ppd.id).total)) > 0 and db.get(Cfdi, ppd.id).pago_manual_fecha is None
