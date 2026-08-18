"""IVA base flujo e ISR provisional por régimen (cálculo puro + endpoints)."""

from datetime import date
from decimal import Decimal

from app.modules.impuestos.calculos import (
    clasificar_regimen,
    isr_provisional,
    isr_tarifa_art96,
    iva_base_flujo,
    tasa_resico_pf,
)
from app.modules.sat.mock_generator import generar_cfdis_mock
from tests.conftest import agregar_membresia, auth_headers, crear_empresa, crear_usuario


class _C:
    def __init__(self, tipo, direccion, estatus="vigente", metodo=None, subtotal=1000, iva=160):
        self.tipo, self.direccion, self.estatus, self.metodo_pago_codigo = tipo, direccion, estatus, metodo
        self.subtotal, self.iva = Decimal(subtotal), Decimal(iva)


def test_iva_base_flujo_separa_pue_rep_ppd_y_no_considerados():
    cfdis = [
        _C("ingreso", "emitido", metodo="PUE", subtotal=10000, iva=1600),
        _C("ingreso", "emitido", metodo="PPD", subtotal=5000, iva=800),  # facturado, no cobrado
        _C("pago", "emitido", subtotal=2000, iva=320),  # REP: cobro de una PPD
        _C("ingreso", "emitido", metodo="PUE", estatus="cancelado", subtotal=999, iva=159.84),
        _C("egreso", "recibido", metodo="PUE", subtotal=3000, iva=480),
        _C("egreso", "recibido", metodo="PPD", subtotal=7000, iva=1120),
        _C("pago", "recibido", subtotal=1000, iva=160),
        _C("nomina", "emitido", subtotal=8000, iva=0),  # sin IVA, se ignora
    ]
    r = iva_base_flujo(cfdis)
    assert r.trasladado_cobrado == Decimal("1920.00")  # 1600 + 320
    assert r.acreditable_pagado == Decimal("640.00")  # 480 + 160
    assert r.saldo == Decimal("1280.00")  # a cargo
    assert r.trasladado_ppd_pendiente == Decimal("800.00")
    assert r.acreditable_ppd_pendiente == Decimal("1120.00")
    e = {f.concepto: f for f in r.emitidas}
    assert (e["PUE"].num_cfdis, e["REP"].num_cfdis, e["PPD pendiente"].num_cfdis, e["No considerados"].num_cfdis) == (1, 1, 1, 1)
    assert e["No considerados"].iva == Decimal("159.84")


def test_clasificacion_de_regimen():
    assert clasificar_regimen(tipo_persona="moral", regimen_codigo="601") == "pm_general"
    assert clasificar_regimen(tipo_persona="moral", regimen_codigo="626") == "pm_resico"
    assert clasificar_regimen(tipo_persona="fisica", regimen_codigo="626") == "pf_resico"
    assert clasificar_regimen(tipo_persona="fisica", regimen_codigo="612") == "pf_actividad"
    assert clasificar_regimen(tipo_persona="fisica", regimen_codigo="605") == "no_aplica"


def test_tarifa_art96_y_tasas_resico():
    # Renglón 3 mensual: (10,000 − 6,332.06) × 10.88 % + 371.83 = 770.90
    assert isr_tarifa_art96(Decimal("10000"), meses=1) == Decimal("770.90")
    # Acumulada a 2 meses: límites y cuota × 2 → (20,000 − 12,664.12) × 10.88 % + 743.66 = 1,541.80
    assert isr_tarifa_art96(Decimal("20000"), meses=2) == Decimal("1541.80")
    assert isr_tarifa_art96(Decimal("0"), meses=1) == 0
    assert tasa_resico_pf(Decimal("20000")) == Decimal("0.0100")
    assert tasa_resico_pf(Decimal("30000")) == Decimal("0.0110")
    assert tasa_resico_pf(Decimal("100000")) == Decimal("0.0200")


def test_isr_pm_general_con_coeficiente():
    r = isr_provisional(
        mecanica="pm_general",
        ingresos_por_mes={1: Decimal("100000"), 2: Decimal("150000"), 3: Decimal("50000")},
        deducciones_por_mes={1: Decimal("40000")},
        hasta_mes=3,
        coeficiente_utilidad=Decimal("0.2000"),
    )
    m1, m2, m3 = r.meses
    # Ene: 100,000 × 0.20 × 30 % = 6,000
    assert (m1.base, m1.isr_acumulado, m1.isr_del_mes) == (Decimal("20000.00"), Decimal("6000.00"), Decimal("6000.00"))
    # Feb: acumulado 250,000 × 0.20 × 30 % = 15,000 − 6,000 pagados = 9,000
    assert (m2.isr_acumulado, m2.pagos_anteriores, m2.isr_del_mes) == (Decimal("15000.00"), Decimal("6000.00"), Decimal("9000.00"))
    # Mar: acumulado 300,000 → 18,000 − 15,000 = 3,000
    assert m3.isr_del_mes == Decimal("3000.00")
    assert not r.advertencias
    # Sin coeficiente: 0 y advertencia
    r0 = isr_provisional(mecanica="pm_general", ingresos_por_mes={1: Decimal("100000")}, deducciones_por_mes={}, hasta_mes=1, coeficiente_utilidad=None)
    assert r0.meses[0].isr_del_mes == 0 and r0.advertencias


def test_isr_pf_actividad_y_resico():
    pf = isr_provisional(
        mecanica="pf_actividad",
        ingresos_por_mes={1: Decimal("30000"), 2: Decimal("30000")},
        deducciones_por_mes={1: Decimal("20000"), 2: Decimal("20000")},
        hasta_mes=2,
        coeficiente_utilidad=None,
    )
    assert pf.meses[0].base == Decimal("10000.00") and pf.meses[0].isr_del_mes == Decimal("770.90")
    assert pf.meses[1].base == Decimal("20000.00") and pf.meses[1].isr_acumulado == Decimal("1541.80")
    assert pf.meses[1].isr_del_mes == Decimal("770.90")

    resico = isr_provisional(
        mecanica="pf_resico",
        ingresos_por_mes={1: Decimal("20000"), 2: Decimal("60000")},
        deducciones_por_mes={1: Decimal("99999")},  # se ignoran
        hasta_mes=2,
        coeficiente_utilidad=None,
    )
    assert resico.meses[0].isr_del_mes == Decimal("200.00")  # 1 %
    assert resico.meses[1].tasa_aplicada == Decimal("0.0150") and resico.meses[1].isr_del_mes == Decimal("900.00")


def _empresa(client, db, seed_rbac, rfc, regimen):
    usuario = crear_usuario(db)
    empresa = crear_empresa(db, rfc=rfc)
    empresa.regimen_fiscal_codigo = regimen
    db.commit()
    agregar_membresia(db, usuario=usuario, empresa=empresa, rol=seed_rbac["administrador"])
    generar_cfdis_mock(db, empresa=empresa, cantidad=80, dias_atras=120, seed=3)
    return auth_headers(client, email=usuario.email, password="Demo1234!", empresa_id=empresa.id), empresa


def test_endpoints_iva_isr_y_configuracion(client, seed_rbac, db):
    headers, empresa = _empresa(client, db, seed_rbac, "NUB010101ABC", "601")  # RFC de 12 → moral
    hoy = date.today()

    iva = client.get(f"/api/v1/impuestos/iva?anio={hoy.year}&mes={hoy.month}", headers=headers)
    assert iva.status_code == 200, iva.text
    b = iva.json()
    assert b["saldo"] == round(b["trasladado_cobrado"] - b["acreditable_pagado"], 2)
    assert {f["concepto"] for f in b["emitidas"]} == {"PUE", "REP", "Notas de crédito", "PPD pendiente", "No considerados"}
    anual = client.get(f"/api/v1/impuestos/iva?anio={hoy.year}", headers=headers).json()
    assert anual["mes"] is None and anual["trasladado_cobrado"] >= b["trasladado_cobrado"]

    # ISR PM sin coeficiente: advertencia y 0
    isr = client.get(f"/api/v1/impuestos/isr?anio={hoy.year}", headers=headers).json()
    assert isr["mecanica"] == "pm_general" and isr["tipo_persona"] == "moral"
    assert isr["advertencias"] and all(m["isr_del_mes"] == 0 for m in isr["meses"])
    assert len(isr["meses"]) == hoy.month

    # Configurar coeficiente → ISR > 0
    cfg = client.put("/api/v1/impuestos/configuracion", headers=headers, json={"coeficiente_utilidad": "0.1250"})
    assert cfg.status_code == 200, cfg.text
    assert cfg.json()["coeficiente_utilidad"] == 0.125 and cfg.json()["mecanica_isr"] == "pm_general"
    isr2 = client.get(f"/api/v1/impuestos/isr?anio={hoy.year}", headers=headers).json()
    assert not isr2["advertencias"]
    ultimo = isr2["meses"][-1]
    assert ultimo["ingresos_acumulados"] > 0
    assert ultimo["isr_acumulado"] == round(round(ultimo["ingresos_acumulados"] * 0.125, 2) * 0.30, 2)
    assert sum(m["isr_del_mes"] for m in isr2["meses"]) == ultimo["isr_acumulado"]

    # Cambiar a RESICO → mecánica pm_resico (flujo)
    client.put("/api/v1/impuestos/configuracion", headers=headers, json={"regimen_fiscal_codigo": "626"})
    assert client.get(f"/api/v1/impuestos/isr?anio={hoy.year}", headers=headers).json()["mecanica"] == "pm_resico"


def test_persona_fisica_por_rfc_de_13(client, seed_rbac, db):
    headers, _ = _empresa(client, db, seed_rbac, "LORM850312MN1", "612")
    isr = client.get("/api/v1/impuestos/isr", headers=headers).json()
    assert isr["tipo_persona"] == "fisica" and isr["mecanica"] == "pf_actividad"
    cfg = client.get("/api/v1/impuestos/configuracion", headers=headers).json()
    assert cfg["tipo_persona"] == "fisica"
