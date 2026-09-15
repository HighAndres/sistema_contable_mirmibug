"""Conciliación semiasistida: el sistema sugiere y el usuario elige.

Cubre pagos en un mes distinto al de emisión (ventana amplia), montos
similares (comisión/redondeo), un movimiento que paga varias facturas (1:N,
con combinaciones sugeridas), una factura cobrada en varios abonos (N:1),
el estado `parcial`, quitar una liga y las validaciones de importe."""

import uuid
from datetime import date
from decimal import Decimal

from app.modules.cfdi.models import Cfdi, CfdiPagoDocto
from app.modules.conciliacion.models import MovimientoBancario
from tests.conftest import agregar_membresia, auth_headers, crear_empresa, crear_usuario

CLIENTE = ("XAXX010101000", "Distribuidora del Norte SA de CV")
OTRO = ("XEXX010101000", "Comercial del Sur SA de CV")
PROVEEDOR = ("PRO900101AB1", "Proveedor Uno SA de CV")
API = "/api/v1/conciliacion/bancos"


def _setup(client, db, seed_rbac):
    usuario = crear_usuario(db)
    empresa = crear_empresa(db, rfc="LMA150101AB1")
    agregar_membresia(db, usuario=usuario, empresa=empresa, rol=seed_rbac["administrador"])
    headers = auth_headers(client, email=usuario.email, password="Demo1234!", empresa_id=empresa.id)
    cuenta = client.post("/api/v1/conciliacion/cuentas", headers=headers, json={"banco": "BBVA", "alias": "Principal"}).json()
    return headers, empresa, cuenta


def _cfdi(db, empresa, *, total, fecha, direccion="emitido", contraparte=CLIENTE, metodo="PPD", tipo="ingreso", folio=None, estatus="vigente"):
    total = Decimal(str(total))
    subtotal = (total / Decimal("1.16")).quantize(Decimal("0.01"))
    rfc, nombre = contraparte
    c = Cfdi(
        empresa_id=empresa.id, uuid_fiscal=str(uuid.uuid4()).upper(), version="4.0", serie="A", folio=folio or str(uuid.uuid4().int % 100000),
        tipo=tipo, direccion=direccion,
        rfc_emisor=empresa.rfc if direccion == "emitido" else rfc, nombre_emisor=empresa.razon_social if direccion == "emitido" else nombre,
        rfc_receptor=rfc if direccion == "emitido" else empresa.rfc, nombre_receptor=nombre if direccion == "emitido" else empresa.razon_social,
        forma_pago_codigo="99" if metodo == "PPD" else "03", metodo_pago_codigo=metodo if tipo in ("ingreso", "egreso") else None,
        subtotal=subtotal, iva=total - subtotal, total=total, fecha=fecha, estatus=estatus,
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def _mov(db, empresa, cuenta, *, fecha, abono=0, cargo=0, concepto="SPEI RECIBIDO"):
    m = MovimientoBancario(
        empresa_id=empresa.id, cuenta_id=uuid.UUID(cuenta["id"]), fecha=fecha, concepto=concepto, referencia=None,
        cargo=Decimal(str(cargo)), abono=Decimal(str(abono)), huella=uuid.uuid4().hex,
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    return m


def _candidatos(client, headers, mov, **params):
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    return client.get(f"{API}/movimientos/{mov.id}/candidatos{'?' + qs if qs else ''}", headers=headers).json()


def test_pago_en_otro_mes_y_monto_similar(client, seed_rbac, db):
    headers, empresa, cuenta = _setup(client, db, seed_rbac)
    factura = _cfdi(db, empresa, total="11600.00", fecha=date(2026, 5, 20))  # emitida en mayo
    abono = _mov(db, empresa, cuenta, fecha=date(2026, 8, 3), abono="11600.00", concepto="SPEI DISTRIBUIDORA DEL NORTE")  # cobrada en agosto
    similar = _mov(db, empresa, cuenta, fecha=date(2026, 8, 4), abono="11587.50", concepto="TRANSFERENCIA")  # −12.50 de comisión

    # Ventana corta (la que usa el auto): no lo ve. Ventana amplia por defecto: exacto, 75 días después.
    assert _candidatos(client, headers, abono, dias_atras=5)["candidatos"] == []
    res = _candidatos(client, headers, abono)
    assert res["movimiento"]["restante"] == 11600.0
    [c] = res["candidatos"]
    assert c["cfdi_id"] == str(factura.id) and c["coincidencia"] == "exacto" and c["dias"] == 75 and c["pagado_despues"] is True
    assert c["contraparte_en_concepto"] is True and c["importe_sugerido"] == 11600.0 and c["metodo_pago"] == "PPD"

    # Monto con comisión: similar dentro del 2 %, y desaparece con tolerancia 0.
    [s] = _candidatos(client, headers, similar)["candidatos"]
    assert s["coincidencia"] == "similar" and s["diferencia"] == 12.5 and s["contraparte_en_concepto"] is False
    assert _candidatos(client, headers, similar, tolerancia_pct=0)["candidatos"][0]["coincidencia"] == "parcial"

    # El auto no liga por ventana corta ni por similitud, pero reporta sugerencias.
    auto = client.post(f"{API}/auto", headers=headers, json={"cuenta_id": cuenta["id"], "tolerancia_dias": 5}).json()
    assert auto == {"revisados": 2, "conciliados": 0, "sin_coincidencia": 0, "ambiguos": 0, "con_sugerencias": 2}
    # Con ventana amplia en el auto, el exacto único sí se liga y el similar sigue como sugerencia.
    auto2 = client.post(f"{API}/auto", headers=headers, json={"cuenta_id": cuenta["id"], "tolerancia_dias": 60}).json()
    assert auto2["conciliados"] == 0  # 60 días no alcanzan (75)
    auto3 = client.post(f"{API}/auto", headers=headers, json={"cuenta_id": cuenta["id"], "tolerancia_dias": 90}).json()
    assert auto3["conciliados"] == 1 and auto3["con_sugerencias"] == 1

    # Buscar por texto ignora monto y ventana
    otra = _cfdi(db, empresa, total="500.00", fecha=date(2025, 1, 10), folio="Z-77")
    porq = _candidatos(client, headers, similar, q="Z-77")["candidatos"]
    assert [c["cfdi_id"] for c in porq] == [str(otra.id)] and porq[0]["coincidencia"] == "menor"


def test_un_abono_paga_varias_facturas_1_a_n(client, seed_rbac, db):
    headers, empresa, cuenta = _setup(client, db, seed_rbac)
    f1 = _cfdi(db, empresa, total="1000.00", fecha=date(2026, 7, 1), folio="1")
    f2 = _cfdi(db, empresa, total="2500.00", fecha=date(2026, 7, 8), folio="2")
    f3 = _cfdi(db, empresa, total="4000.00", fecha=date(2026, 7, 15), folio="3")
    _cfdi(db, empresa, total="4000.00", fecha=date(2026, 7, 15), folio="9", contraparte=OTRO)  # mismo monto, otro cliente: no entra en la combinación
    _cfdi(db, empresa, total="7500.00", fecha=date(2026, 7, 20), folio="C", estatus="cancelado")  # cancelada: nunca candidata
    abono = _mov(db, empresa, cuenta, fecha=date(2026, 8, 1), abono="7500.00", concepto="PAGO FACTURAS 1 2 3 DISTRIBUIDORA NORTE")

    res = _candidatos(client, headers, abono)
    por_id = {c["cfdi_id"]: c for c in res["candidatos"]}
    assert set(por_id) == {str(f1.id), str(f2.id), str(f3.id)} | {c for c in por_id if por_id[c]["rfc_contraparte"] == OTRO[0]}
    assert all(c["coincidencia"] == "menor" for c in por_id.values())
    [combo] = res["combinaciones"]
    assert set(combo["cfdi_ids"]) == {str(f1.id), str(f2.id), str(f3.id)} and combo["total"] == 7500.0 and combo["diferencia"] == 0
    assert combo["rfc_contraparte"] == CLIENTE[0]

    # El usuario acepta la combinación → 3 ligas, movimiento conciliado, sin restante.
    res = client.post(f"{API}/movimientos/{abono.id}/conciliar", headers=headers, json={"ligas": [{"cfdi_id": i} for i in combo["cfdi_ids"]], "nota": "Pago de 3 facturas"})
    assert res.status_code == 200, res.text
    m = res.json()
    assert m["estado"] == "conciliado" and m["importe_ligado"] == 7500.0 and m["restante"] == 0 and len(m["ligas"]) == 3
    assert sorted(l["importe"] for l in m["ligas"]) == [1000.0, 2500.0, 4000.0]
    assert m["cfdi_nombre"].startswith("3 CFDI") and m["nota"] == "Pago de 3 facturas"

    # Ya no hay nada por ligar y esas facturas dejan de ser candidatas para otro abono
    assert _candidatos(client, headers, abono)["candidatos"] == []
    otro = _mov(db, empresa, cuenta, fecha=date(2026, 8, 2), abono="1000.00")
    assert str(f1.id) not in {c["cfdi_id"] for c in _candidatos(client, headers, otro)["candidatos"]}

    # Quitar una sola liga → parcial con el restante de esa factura
    m2 = client.delete(f"{API}/movimientos/{abono.id}/ligas/{f2.id}", headers=headers).json()
    assert m2["estado"] == "parcial" and m2["restante"] == 2500.0 and len(m2["ligas"]) == 2
    assert client.delete(f"{API}/movimientos/{abono.id}/ligas/{f2.id}", headers=headers).status_code == 404
    # y f2 vuelve a ser candidata exacta por lo que falta
    [c] = [c for c in _candidatos(client, headers, abono)["candidatos"] if c["cfdi_id"] == str(f2.id)]
    assert c["coincidencia"] == "exacto"

    # El resumen del mes cuenta lo parcial por importe ligado
    r = client.get("/api/v1/conciliacion/resumen?anio=2026&mes=8", headers=headers).json()["banco"]
    assert r["parciales"] == 1 and r["abonos_conciliados"] == 5000.0 and r["pendientes"] == 1


def test_una_factura_cobrada_en_varios_abonos_n_a_1(client, seed_rbac, db):
    headers, empresa, cuenta = _setup(client, db, seed_rbac)
    factura = _cfdi(db, empresa, total="10000.00", fecha=date(2026, 6, 10))
    a1 = _mov(db, empresa, cuenta, fecha=date(2026, 7, 5), abono="6000.00")
    a2 = _mov(db, empresa, cuenta, fecha=date(2026, 8, 5), abono="4000.00")
    a3 = _mov(db, empresa, cuenta, fecha=date(2026, 8, 6), abono="4000.00")

    # Primer abono: la factura es mayor → parcial; se liga con el importe del abono
    [c] = _candidatos(client, headers, a1)["candidatos"]
    assert c["coincidencia"] == "parcial" and c["saldo"] == 10000.0 and c["importe_sugerido"] == 6000.0
    m1 = client.post(f"{API}/movimientos/{a1.id}/conciliar", headers=headers, json={"cfdi_id": str(factura.id)}).json()
    assert m1["estado"] == "conciliado" and m1["ligas"][0]["importe"] == 6000.0

    # Segundo abono: ahora el saldo de la factura es exactamente 4,000
    [c] = _candidatos(client, headers, a2)["candidatos"]
    assert c["coincidencia"] == "exacto" and c["saldo"] == 4000.0 and c["ligado_otros"] == 6000.0
    m2 = client.post(f"{API}/movimientos/{a2.id}/conciliar", headers=headers, json={"cfdi_id": str(factura.id)}).json()
    assert m2["estado"] == "conciliado"

    # Tercer abono: la factura ya está cubierta → sin candidatos y la liga se rechaza
    assert _candidatos(client, headers, a3)["candidatos"] == []
    res = client.post(f"{API}/movimientos/{a3.id}/conciliar", headers=headers, json={"cfdi_id": str(factura.id)})
    assert res.status_code == 422 and "cubierto" in res.json()["detail"]

    # Si se desliga el primero, el tercero ya puede cobrar el saldo liberado
    client.post(f"{API}/movimientos/{a1.id}/desconciliar", headers=headers)
    [c] = _candidatos(client, headers, a3)["candidatos"]
    assert c["coincidencia"] == "parcial" and c["saldo"] == 6000.0


def test_parcial_importes_y_validaciones(client, seed_rbac, db):
    headers, empresa, cuenta = _setup(client, db, seed_rbac)
    f_chica = _cfdi(db, empresa, total="6000.00", fecha=date(2026, 7, 1))
    f_grande = _cfdi(db, empresa, total="9000.00", fecha=date(2026, 7, 2))
    recibida = _cfdi(db, empresa, total="4000.00", fecha=date(2026, 7, 3), direccion="recibido", contraparte=PROVEEDOR, tipo="egreso", metodo="PUE")
    abono = _mov(db, empresa, cuenta, fecha=date(2026, 8, 1), abono="10000.00")

    # Liga a una factura menor → parcial, restante 4,000
    m = client.post(f"{API}/movimientos/{abono.id}/conciliar", headers=headers, json={"cfdi_id": str(f_chica.id)}).json()
    assert m["estado"] == "parcial" and m["importe_ligado"] == 6000.0 and m["restante"] == 4000.0
    # aparece en el filtro de parciales
    parciales = client.get(f"{API}/movimientos?estado=parcial", headers=headers).json()
    assert [x["id"] for x in parciales["items"]] == [str(abono.id)]

    # Importe explícito mayor al restante del movimiento → 422
    res = client.post(f"{API}/movimientos/{abono.id}/conciliar", headers=headers, json={"ligas": [{"cfdi_id": str(f_grande.id), "importe": "4500.00"}]})
    assert res.status_code == 422 and "falta al movimiento" in res.json()["detail"]
    # Un abono no se liga con un CFDI recibido
    res = client.post(f"{API}/movimientos/{abono.id}/conciliar", headers=headers, json={"cfdi_id": str(recibida.id)})
    assert res.status_code == 422 and "abono" in res.json()["detail"]
    # Sin cfdi_id ni ligas → 422 de validación
    assert client.post(f"{API}/movimientos/{abono.id}/conciliar", headers=headers, json={"nota": "x"}).status_code == 422

    # Importe explícito parcial sobre la grande: completa el movimiento y deja saldo en la factura
    m = client.post(f"{API}/movimientos/{abono.id}/conciliar", headers=headers, json={"ligas": [{"cfdi_id": str(f_grande.id), "importe": "4000.00"}]}).json()
    assert m["estado"] == "conciliado" and m["restante"] == 0 and {l["cfdi_id"]: l["importe"] for l in m["ligas"]} == {str(f_chica.id): 6000.0, str(f_grande.id): 4000.0}

    # Otro abono ve a la grande con saldo 5,000 (9,000 − 4,000 ligado)
    otro = _mov(db, empresa, cuenta, fecha=date(2026, 8, 2), abono="5000.00")
    [c] = [c for c in _candidatos(client, headers, otro)["candidatos"] if c["cfdi_id"] == str(f_grande.id)]
    assert c["coincidencia"] == "exacto" and c["ligado_otros"] == 4000.0 and c["saldo"] == 5000.0

    # Un cargo se liga con CFDI recibidos (gasto) y no con emitidos
    cargo = _mov(db, empresa, cuenta, fecha=date(2026, 8, 3), cargo="4000.00", concepto="PAGO PROVEEDOR UNO")
    [c] = _candidatos(client, headers, cargo)["candidatos"]
    assert c["cfdi_id"] == str(recibida.id) and c["coincidencia"] == "exacto" and c["contraparte_en_concepto"] is True

    # Ignorado no se puede ligar hasta volver a pendiente
    client.post(f"{API}/movimientos/{cargo.id}/ignorar", headers=headers, json={"nota": "x"})
    assert client.post(f"{API}/movimientos/{cargo.id}/conciliar", headers=headers, json={"cfdi_id": str(recibida.id)}).status_code == 422


def test_ppd_con_rep_solo_ofrece_el_saldo(client, seed_rbac, db):
    """Una factura PPD con complemento de pago parcial ofrece solo lo que falta;
    el REP mismo es candidato por su monto."""
    headers, empresa, cuenta = _setup(client, db, seed_rbac)
    ppd = _cfdi(db, empresa, total="11600.00", fecha=date(2026, 6, 1))
    rep = _cfdi(db, empresa, total="5000.00", fecha=date(2026, 7, 1), tipo="pago", metodo=None)
    rep.pagos_relacionados.append(CfdiPagoDocto(uuid_relacionado=ppd.uuid_fiscal, imp_pagado=Decimal("5000.00"), iva_pagado=Decimal("689.66"), fecha_pago=date(2026, 7, 1)))
    db.commit()
    abono = _mov(db, empresa, cuenta, fecha=date(2026, 7, 2), abono="5000.00")
    res = _candidatos(client, headers, abono)["candidatos"]
    por_id = {c["cfdi_id"]: c for c in res}
    assert por_id[str(rep.id)]["coincidencia"] == "exacto" and por_id[str(rep.id)]["tipo"] == "pago"
    assert por_id[str(ppd.id)]["pagado_rep"] == 5000.0 and por_id[str(ppd.id)]["saldo"] == 6600.0 and por_id[str(ppd.id)]["coincidencia"] == "parcial"
    assert res[0]["cfdi_id"] == str(rep.id)  # el exacto va primero
