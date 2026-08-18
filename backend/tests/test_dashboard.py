"""Dashboard por periodo (IVA/ISR del módulo impuestos, cuentas por cobrar/pagar,
alertas explicadas), vigencias FIEL/CSD y documentos SAT simulados."""

from datetime import date, timedelta

from app.modules.credentials.crud import estado_vigencia
from app.modules.sat.mock_generator import generar_cfdis_mock
from tests.conftest import agregar_membresia, auth_headers, crear_empresa, crear_usuario


def _setup(client, db, seed_rbac):
    usuario = crear_usuario(db)
    empresa = crear_empresa(db)
    agregar_membresia(db, usuario=usuario, empresa=empresa, rol=seed_rbac["administrador"])
    cfdis = generar_cfdis_mock(db, empresa=empresa, cantidad=100, dias_atras=150, seed=5)
    return auth_headers(client, email=usuario.email, password="Demo1234!", empresa_id=empresa.id), empresa, cfdis


def test_dashboard_por_periodo(client, seed_rbac, db):
    headers, empresa, cfdis = _setup(client, db, seed_rbac)
    hoy = date.today()

    hist = client.get("/api/v1/reports/dashboard", headers=headers).json()
    mes = client.get(f"/api/v1/reports/dashboard?anio={hoy.year}&mes={hoy.month}", headers=headers).json()
    anual = client.get(f"/api/v1/reports/dashboard?anio={hoy.year}", headers=headers).json()

    assert hist["ingresos_total"] >= anual["ingresos_total"] >= mes["ingresos_total"]
    assert mes["mes"] == hoy.month and anual["mes"] is None
    # IVA del dashboard = IVA del módulo impuestos para el mismo periodo
    iva = client.get(f"/api/v1/impuestos/iva?anio={hoy.year}&mes={hoy.month}", headers=headers).json()
    assert mes["iva_saldo"] == iva["saldo"] == mes["iva_por_pagar"]
    # ISR mensual = pago provisional del mes; anual = acumulado
    isr = client.get(f"/api/v1/impuestos/isr?anio={hoy.year}&hasta_mes={hoy.month}", headers=headers).json()
    assert mes["isr_estimado"] == isr["meses"][-1]["isr_del_mes"]
    assert anual["isr_estimado"] == isr["meses"][-1]["isr_acumulado"]
    assert mes["isr_mecanica"] == "pm_general"
    # Cuentas por cobrar = ingresos PPD vigentes del periodo
    cxc = [c for c in cfdis if c.tipo == "ingreso" and c.metodo_pago_codigo == "PPD" and c.estatus == "vigente"]
    assert hist["cuentas_por_cobrar"]["num_cfdis"] == len(cxc)
    assert abs(hist["cuentas_por_cobrar"]["total"] - float(sum(c.total for c in cxc))) < 0.01
    assert isinstance(hist["alertas_por_regla"], list)


def test_top_clientes_y_proveedores_por_periodo(client, seed_rbac, db):
    headers, _, _ = _setup(client, db, seed_rbac)
    hoy = date.today()
    cli = client.get(f"/api/v1/reports/top-clientes?anio={hoy.year}", headers=headers).json()
    prov = client.get(f"/api/v1/reports/top-proveedores?anio={hoy.year}", headers=headers).json()
    assert cli and prov
    assert cli == sorted(cli, key=lambda x: -x["monto_total"])
    assert all(p["rfc"] and p["num_cfdis"] > 0 for p in prov)


def test_vigencias_y_estado():
    hoy = date(2026, 8, 18)
    assert estado_vigencia(None, hoy=hoy) == ("sin_datos", None)
    assert estado_vigencia(hoy - timedelta(days=3), hoy=hoy) == ("vencida", -3)
    assert estado_vigencia(hoy + timedelta(days=20), hoy=hoy) == ("por_vencer", 20)
    assert estado_vigencia(hoy + timedelta(days=400), hoy=hoy) == ("vigente", 400)


def test_vigencias_endpoint_y_documentos(client, seed_rbac, db):
    headers, _, _ = _setup(client, db, seed_rbac)
    v = client.get("/api/v1/credentials/vigencias", headers=headers).json()
    assert v["conectado"] is False and v["fiel"]["estado"] == "sin_datos"

    client.post("/api/v1/credentials/conectar", headers=headers, json={"tipo": "efirma"})
    v = client.get("/api/v1/credentials/vigencias", headers=headers).json()
    assert v["conectado"] and v["fiel"]["vence"] and v["fiel"]["estado"] in ("vigente", "por_vencer")
    assert v["csd"]["numero_serie"].startswith("3000100000050")

    for ruta in ("/api/v1/sat/constancia", "/api/v1/sat/opinion"):
        res = client.get(ruta, headers=headers)
        assert res.status_code == 200
        assert res.headers["content-type"] == "application/pdf"
        assert res.content.startswith(b"%PDF-1.4") and b"%%EOF" in res.content
        assert b"SIMULADO" in res.content
    assert client.get("/api/v1/sat/opinion?sentido=raro", headers=headers).status_code == 422
