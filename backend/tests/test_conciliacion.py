"""Conciliación: importador flexible de estados de cuenta (xlsx/csv), auto y manual
contra CFDI, declaraciones y resumen SAT / banco / declarado."""

import io
from datetime import date, timedelta
from decimal import Decimal

import openpyxl

from app.modules.conciliacion.importador import ImportacionError, importar_estado_cuenta
from app.modules.sat.mock_generator import generar_cfdis_mock
from tests.conftest import agregar_membresia, auth_headers, crear_empresa, crear_usuario


def _xlsx(filas: list[list], titulo_extra=True) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    if titulo_extra:  # filas de logo/título antes del encabezado, como los bancos reales
        ws.append(["BANCO DEMO S.A."])
        ws.append(["Estado de cuenta", None, "Cuenta 1234"])
        ws.append([])
    for f in filas:
        ws.append(f)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_importador_excel_cargo_abono_con_encabezado_desplazado():
    contenido = _xlsx(
        [
            ["Fecha", "Descripción", "Referencia", "Retiros", "Depósitos", "Saldo"],
            ["01/07/2026", "SPEI RECIBIDO CLIENTE X", "0012345", None, "11,600.00", "50,000.00"],
            ["02/07/2026", "PAGO PROVEEDOR Y", "9988", "$4,640.00", None, "45,360.00"],
            ["03/07/2026", "COMISION MANEJO CTA", None, 150, None, 45210],
            [None, "TOTAL", None, 4790, 11600, None],  # sin fecha: se omite
        ]
    )
    filas, mapa, adv = importar_estado_cuenta(contenido, "edo_cta.xlsx")
    assert {"fecha", "concepto", "referencia", "cargo", "abono", "saldo"} <= set(mapa)
    assert len(filas) == 3
    assert (filas[0].abono, filas[0].cargo, filas[0].fecha) == (Decimal("11600.00"), Decimal("0.00"), date(2026, 7, 1))
    assert filas[1].cargo == Decimal("4640.00") and filas[1].referencia == "9988"
    assert filas[2].saldo == Decimal("45210.00")
    assert any("omitieron" in a for a in adv)
    # Huella estable y distinta por fila
    assert len({f.huella for f in filas}) == 3


def test_importador_csv_importe_con_signo_y_punto_y_coma():
    csv = (
        "Fecha;Concepto;Importe\n"
        "2026-07-05;DEPOSITO EN EFECTIVO;2500.50\n"
        "2026-07-06;CARGO TARJETA;-1200\n"
        "2026-07-07;INTERESES;(35.00)\n"
    ).encode("utf-8")
    filas, mapa, _ = importar_estado_cuenta(csv, "movs.csv")
    assert "importe" in mapa and "cargo" not in mapa
    assert [(f.abono, f.cargo) for f in filas] == [
        (Decimal("2500.50"), Decimal("0.00")),
        (Decimal("0.00"), Decimal("1200.00")),
        (Decimal("0.00"), Decimal("35.00")),
    ]


def test_importador_rechaza_sin_columnas():
    try:
        importar_estado_cuenta(b"hola,mundo\n1,2\n", "x.csv")
        assert False, "debió fallar"
    except ImportacionError:
        pass


def _setup(client, db, seed_rbac):
    usuario = crear_usuario(db)
    empresa = crear_empresa(db)
    agregar_membresia(db, usuario=usuario, empresa=empresa, rol=seed_rbac["administrador"])
    cfdis = generar_cfdis_mock(db, empresa=empresa, cantidad=60, dias_atras=90, seed=9)
    headers = auth_headers(client, email=usuario.email, password="Demo1234!", empresa_id=empresa.id)
    cuenta = client.post("/api/v1/conciliacion/cuentas", headers=headers, json={"banco": "BBVA", "alias": "Principal", "numero": "1234"}).json()
    return headers, empresa, cfdis, cuenta


def test_flujo_completo_importar_auto_manual_declarar_resumen(client, seed_rbac, db):
    headers, empresa, cfdis, cuenta = _setup(client, db, seed_rbac)

    # Estado de cuenta construido a partir de CFDIs reales de la bóveda:
    # 1 ingreso PUE cobrado exacto, 1 gasto pagado exacto, 1 abono sin CFDI, 1 comisión.
    ingreso = next(c for c in cfdis if c.tipo == "ingreso" and c.metodo_pago_codigo == "PUE" and c.estatus == "vigente")
    egreso = next(c for c in cfdis if c.tipo == "egreso" and c.metodo_pago_codigo == "PUE" and c.estatus == "vigente")
    filas = [
        ["Fecha", "Concepto", "Referencia", "Cargo", "Abono", "Saldo"],
        [ingreso.fecha.strftime("%d/%m/%Y"), f"SPEI {ingreso.nombre_receptor}", "A1", None, float(ingreso.total), 100000],
        [(egreso.fecha + timedelta(days=1)).strftime("%d/%m/%Y"), f"PAGO {egreso.nombre_emisor}", "B2", float(egreso.total), None, 90000],
        [ingreso.fecha.strftime("%d/%m/%Y"), "DEPOSITO SIN FACTURA", "C3", None, 777.77, 90777.77],
        [ingreso.fecha.strftime("%d/%m/%Y"), "COMISION", None, 58, None, 90719.77],
    ]
    res = client.post(
        "/api/v1/conciliacion/bancos/importar",
        headers=headers,
        files={"archivo": ("edo.xlsx", _xlsx(filas), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        data={"cuenta_id": cuenta["id"]},
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["importados"] == 4 and body["duplicados"] == 0
    # Reimportar el mismo archivo no duplica
    res2 = client.post("/api/v1/conciliacion/bancos/importar", headers=headers, files={"archivo": ("edo.xlsx", _xlsx(filas), "application/octet-stream")}, data={"cuenta_id": cuenta["id"]})
    assert res2.json()["importados"] == 0 and res2.json()["duplicados"] == 4

    # Auto-conciliación: liga los 2 con CFDI exacto (si no hay ambigüedad de monto)
    auto = client.post("/api/v1/conciliacion/bancos/auto", headers=headers, json={"cuenta_id": cuenta["id"], "tolerancia_dias": 5}).json()
    assert auto["revisados"] == 4
    assert auto["conciliados"] + auto["ambiguos"] >= 2
    movs = client.get(f"/api/v1/conciliacion/bancos/movimientos?cuenta_id={cuenta['id']}&limit=50", headers=headers).json()
    assert movs["total"] == 4
    por_ref = {m["referencia"]: m for m in movs["items"] if m["referencia"]}
    if por_ref["A1"]["estado"] == "conciliado":
        assert por_ref["A1"]["cfdi_uuid"] == ingreso.uuid_fiscal and por_ref["A1"]["conciliado_por"] == "auto"

    # El depósito sin factura no tiene candidatos; se ignora manualmente
    dep = por_ref["C3"]
    assert client.get(f"/api/v1/conciliacion/bancos/movimientos/{dep['id']}/candidatos", headers=headers).json() == []
    ig = client.post(f"/api/v1/conciliacion/bancos/movimientos/{dep['id']}/ignorar", headers=headers, json={"nota": "Aportación de socio"}).json()
    assert ig["estado"] == "ignorado" and ig["nota"] == "Aportación de socio"

    # Conciliación manual: candidatos del pago al proveedor incluyen el CFDI del gasto
    pago = por_ref["B2"]
    cands = client.get(f"/api/v1/conciliacion/bancos/movimientos/{pago['id']}/candidatos", headers=headers).json()
    assert any(c["cfdi_id"] == str(egreso.id) for c in cands)
    man = client.post(f"/api/v1/conciliacion/bancos/movimientos/{pago['id']}/conciliar", headers=headers, json={"cfdi_id": str(egreso.id)}).json()
    assert man["estado"] == "conciliado" and man["conciliado_por"] == "manual" and man["cfdi_total"] == float(egreso.total)
    des = client.post(f"/api/v1/conciliacion/bancos/movimientos/{pago['id']}/desconciliar", headers=headers).json()
    assert des["estado"] == "pendiente" and des["cfdi_id"] is None

    # Declaración del mes del ingreso + resumen a tres columnas
    anio, mes = ingreso.fecha.year, ingreso.fecha.month
    r0 = client.get(f"/api/v1/conciliacion/resumen?anio={anio}&mes={mes}", headers=headers).json()
    assert r0["semaforo"] == "sin_declaracion" and r0["declarado"]["capturada"] is False
    assert r0["banco"]["num_movimientos"] >= 3 and r0["sat"]["num_cfdis"] > 0

    iva_sat = r0["sat"]["iva_saldo"]
    dec = client.put(f"/api/v1/conciliacion/declaraciones/{anio}/{mes}", headers=headers, json={"iva_declarado": iva_sat, "isr_declarado": r0["sat"]["isr_estimado"], "ingresos_declarados": r0["sat"]["ingresos_cobrados"], "fecha_presentacion": "2026-08-17"}).json()
    assert dec["capturada"] and dec["iva_declarado"] == iva_sat
    r1 = client.get(f"/api/v1/conciliacion/resumen?anio={anio}&mes={mes}", headers=headers).json()
    assert r1["semaforo"] == "ok"
    assert r1["diferencias"]["iva_sat_vs_declarado"] == 0 and r1["diferencias"]["isr_sat_vs_declarado"] == 0

    # Diferencia → revisar
    client.put(f"/api/v1/conciliacion/declaraciones/{anio}/{mes}", headers=headers, json={"iva_declarado": iva_sat + 500})
    r2 = client.get(f"/api/v1/conciliacion/resumen?anio={anio}&mes={mes}", headers=headers).json()
    assert r2["semaforo"] == "revisar" and r2["diferencias"]["iva_sat_vs_declarado"] == -500


def test_importar_archivo_invalido_y_cuenta_duplicada(client, seed_rbac, db):
    headers, _, _, cuenta = _setup(client, db, seed_rbac)
    res = client.post("/api/v1/conciliacion/bancos/importar", headers=headers, files={"archivo": ("x.csv", b"a,b\n1,2\n", "text/csv")}, data={"cuenta_id": cuenta["id"]})
    assert res.status_code == 422
    assert client.post("/api/v1/conciliacion/cuentas", headers=headers, json={"banco": "Otro", "alias": "principal"}).status_code == 409
