"""Pedimentos de importación: parser M3, motor de costeo (contra el papel de
trabajo en Excel) y flujo completo importar → configurar → aplicar al inventario."""

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import pytest

from app.modules.pedimentos.costeo import costear, prorratear
from app.modules.pedimentos.parser_m3 import M3ParseError, parse_m3
from tests.conftest import agregar_membresia, auth_headers, crear_empresa, crear_usuario

FIXTURE_M3 = Path(__file__).parent / "fixtures" / "m3382475.003"


# ---------- Parser ----------


def test_parser_m3_cuadra_con_el_pedimento_impreso():
    m3 = parse_m3(FIXTURE_M3.read_bytes())
    # Encabezado (registro 501) — valores tomados del PDF del pedimento.
    assert m3.numero_completo == "26 51 3382 6000018"
    assert m3.tipo_cambio == Decimal("18.43080")
    assert m3.rfc_importador == "LMA171222GB7"
    assert str(m3.fecha_pago) == "2026-01-03"
    assert m3.incoterm == "CIF"
    assert m3.contenedores == ["EMCU8886850"]
    # Cuadro de liquidación del PDF: DTA 3,344 · IGI 109,796 · IVA 84,989 · PRV 330 · REC 1,614
    assert m3.dta == Decimal("3344")
    assert m3.otras_contribuciones == {"REC": "1614", "PRV": "330", "IVA/PRV": "53"}
    assert len(m3.partidas) == 19
    assert m3.igi_total == Decimal("109796")
    assert m3.iva_total == Decimal("84989")
    assert m3.valor_aduana_total == Decimal("418045")
    assert m3.valor_usd_total == Decimal("22681.88")
    p1 = m3.partidas[0]
    assert (p1.fraccion, p1.descripcion, p1.umc_clave) == ("68029991", "PIEDRAS DECORATIVAS", "6")
    assert (p1.precio_unitario * p1.cantidad_umc).quantize(Decimal("1")) == p1.valor_comercial  # 0.73723 × 2976 ≈ 2194
    assert (p1.igi, p1.iva, p1.tasa_igi) == (Decimal("331"), Decimal("407"), Decimal("15"))


def test_parser_rechaza_archivos_que_no_son_m3():
    with pytest.raises(M3ParseError):
        parse_m3(b"esto no es un pedimento")
    with pytest.raises(M3ParseError):
        parse_m3(b"")


# ---------- Costeo (replica del Excel) ----------


@dataclass
class _P:
    secuencia: int
    precio_unitario: Decimal
    valor_aduana: Decimal
    cantidad_umc: Decimal
    cantidad_umt: Decimal | None
    igi: Decimal
    iva: Decimal


def test_costeo_replica_papel_de_trabajo_excel():
    """Fila 7 de 'PAPEL COSTOS final.xlsx' (pedimento 26 16 3382 6000018, 11 partidas,
    DTA 4,734, utilidad fija 500, prorrateo por partes iguales):
    J=2.70019, H=42300, N(IGI)=0, O(IVA imp)=18421 → AC (precio venta)=2.7114386…, AJ=-69.98"""
    partidas = [_P(1, Decimal("2.70019"), Decimal("114218"), Decimal("42300"), None, Decimal("0"), Decimal("18421"))]
    partidas += [_P(i, Decimal("1"), Decimal("1000"), Decimal("10"), None, Decimal("0"), Decimal("0")) for i in range(2, 12)]

    r = costear(partidas, dta=Decimal("4734"), utilidad=Decimal("500"), metodo_prorrateo="partes_iguales")
    p = r.partidas[0]
    assert p.dta_asignado == Decimal("430.36")  # 4734 / 11 (col R)
    assert p.dta_pza == Decimal("0.010174")  # col S
    assert p.igi_pza == Decimal("0")  # col U
    assert p.utilidad_pza == Decimal("0.001074")  # 45.45/42300 (col AA; Excel 0.0010746 sin redondear)
    assert p.costo_unitario == Decimal("2.710364")  # sin utilidad (landed)
    assert p.precio_unitario_venta == Decimal("2.711438")  # col AC (Excel: 2.711438656…)
    assert p.dif_iva == Decimal("-69.99")  # col AJ (Excel: -69.98, diferencia por redondeo a 6 dec)
    # Los prorrateos siempre cuadran al centavo con el monto original.
    assert sum(x.dta_asignado for x in r.partidas) == Decimal("4734.00")
    assert sum(x.utilidad_asignada for x in r.partidas) == Decimal("500.00")


def test_costeo_con_gastos_adicionales_como_fila_18_del_excel():
    """Fila 18: W (fletes)=52,680 sobre 5 partidas, H=2140 → X = 52680/5/2140 = 4.923364"""
    partidas = [_P(1, Decimal("155.44813"), Decimal("332659"), Decimal("2140"), None, Decimal("72858"), Decimal("70410"))]
    partidas += [_P(i, Decimal("1"), Decimal("1000"), Decimal("500"), None, Decimal("0"), Decimal("0")) for i in range(2, 6)]
    r = costear(partidas, dta=Decimal("4853"), gastos_adicionales=Decimal("52680"), utilidad=Decimal("500"))
    p = r.partidas[0]
    assert p.gastos_pza == Decimal("4.923364")
    assert p.igi_pza == Decimal("34.045794")  # 72858/2140 (col U)
    assert p.dta_pza == Decimal("0.453551")  # 4853/5/2140 (col S)
    assert p.precio_unitario_venta == pytest.approx(Decimal("194.917569"), abs=Decimal("0.00001"))  # col AC = 194.9175692…


def test_prorrateo_por_valor_aduana_cantidad_y_peso():
    partidas = [
        _P(1, Decimal("1"), Decimal("300"), Decimal("10"), Decimal("5"), Decimal("0"), Decimal("0")),
        _P(2, Decimal("1"), Decimal("100"), Decimal("30"), Decimal("15"), Decimal("0"), Decimal("0")),
    ]
    assert prorratear(Decimal("100"), partidas, "partes_iguales") == [Decimal("50.00"), Decimal("50.00")]
    assert prorratear(Decimal("100"), partidas, "valor_aduana") == [Decimal("75.00"), Decimal("25.00")]
    assert prorratear(Decimal("100"), partidas, "cantidad") == [Decimal("25.00"), Decimal("75.00")]
    assert prorratear(Decimal("100"), partidas, "peso") == [Decimal("25.00"), Decimal("75.00")]
    # Residuo de redondeo lo absorbe la última partida: 100/3 → 33.33 + 33.33 + 33.34
    tres = partidas + [_P(3, Decimal("1"), Decimal("1"), Decimal("1"), None, Decimal("0"), Decimal("0"))]
    assert sum(prorratear(Decimal("100"), tres, "partes_iguales")) == Decimal("100.00")


# ---------- API: flujo completo ----------


def _empresa_admin(db, seed_rbac, rfc="LMA171222GB7"):
    usuario = crear_usuario(db)
    empresa = crear_empresa(db, rfc=rfc, razon_social="Logística Multimodal de América SA de CV")
    agregar_membresia(db, usuario=usuario, empresa=empresa, rol=seed_rbac["administrador"])
    return usuario, empresa


def _importar(client, headers, referencia=None):
    with FIXTURE_M3.open("rb") as f:
        data = {"referencia": referencia} if referencia else {}
        return client.post(
            "/api/v1/pedimentos/importar",
            headers=headers,
            files={"archivo": ("m3382475.003", f, "application/octet-stream")},
            data=data,
        )


def test_importar_m3_crea_pedimento_con_costeo(client, seed_rbac, db):
    usuario, empresa = _empresa_admin(db, seed_rbac)
    headers = auth_headers(client, email=usuario.email, password="Demo1234!", empresa_id=empresa.id)

    res = _importar(client, headers, referencia="LMA26-019")
    assert res.status_code == 201, res.text
    body = res.json()
    ped = body["pedimento"]
    assert ped["numero_completo"] == "26 51 3382 6000018"
    assert ped["referencia"] == "LMA26-019"
    assert ped["num_partidas"] == 19
    assert ped["dta"] == 3344
    assert ped["igi_total"] == 109796
    assert ped["iva_total"] == 84989
    assert ped["estatus"] == "borrador"
    assert ped["origen"] == "m3"
    # El RFC coincide con la empresa → no hay advertencia de RFC; sí de productos sin catálogo.
    assert not any("RFC" in a for a in body["advertencias"])
    assert any("no coinciden con ningún producto" in a for a in body["advertencias"])

    # Costeo calculado por partida: sin gastos ni utilidad, costo = precio + dta/pza + igi/pza
    p1 = ped["partidas"][0]
    assert p1["descripcion"] == "PIEDRAS DECORATIVAS"
    assert p1["umc_descripcion"] == "PIEZA"
    assert p1["clave_unidad_sat"] == "H87"
    assert p1["costeo"]["dta_asignado"] == pytest.approx(3344 / 19, abs=0.01)
    assert p1["costeo"]["igi_pza"] == pytest.approx(331 / 2976, abs=1e-6)
    assert p1["costeo"]["costo_unitario"] == pytest.approx(0.73723 + 3344 / 19 / 2976 + 331 / 2976, abs=1e-5)
    assert p1["costeo"]["utilidad_pza"] == 0
    assert ped["resumen"]["iva_importacion_total"] == 84989

    # Duplicado → 409
    assert _importar(client, headers).status_code == 409

    # Aparece en la lista
    lista = client.get("/api/v1/pedimentos", headers=headers).json()
    assert len(lista) == 1 and lista[0]["numero_completo"] == "26 51 3382 6000018"


def test_importar_archivo_invalido_regresa_422(client, seed_rbac, db):
    usuario, empresa = _empresa_admin(db, seed_rbac)
    headers = auth_headers(client, email=usuario.email, password="Demo1234!", empresa_id=empresa.id)
    res = client.post(
        "/api/v1/pedimentos/importar",
        headers=headers,
        files={"archivo": ("basura.txt", b"hola mundo", "text/plain")},
    )
    assert res.status_code == 422


def test_configurar_costeo_y_aplicar_al_inventario(client, seed_rbac, db):
    usuario, empresa = _empresa_admin(db, seed_rbac)
    headers = auth_headers(client, email=usuario.email, password="Demo1234!", empresa_id=empresa.id)
    ped_id = _importar(client, headers).json()["pedimento"]["id"]

    # Configurar: fletes + utilidad + prorrateo por valor aduana → se recalcula al vuelo
    res = client.patch(
        f"/api/v1/pedimentos/{ped_id}",
        headers=headers,
        json={
            "gastos_adicionales": [{"concepto": "Flete marítimo", "monto": 52680}, {"concepto": "Maniobras", "monto": 3200}],
            "utilidad": 500,
            "metodo_prorrateo": "valor_aduana",
        },
    )
    assert res.status_code == 200, res.text
    ped = res.json()
    assert ped["resumen"]["gastos_adicionales"] == 55880
    assert ped["metodo_prorrateo"] == "valor_aduana"
    # Por valor aduana: partida 1 vale 2194 de 418045 → recibe ese % del DTA
    p1 = ped["partidas"][0]
    assert p1["costeo"]["dta_asignado"] == pytest.approx(3344 * 2194 / 418045, abs=0.01)
    assert p1["costeo"]["gastos_asignados"] == pytest.approx(55880 * 2194 / 418045, abs=0.01)
    assert p1["costeo"]["precio_unitario_venta"] > p1["costeo"]["costo_unitario"]  # lleva utilidad
    assert ped["resumen"]["total_venta"] == pytest.approx(ped["resumen"]["subtotal_venta"] * 1.16, abs=0.5)

    # Corregir clave SAT de una partida
    res = client.patch(
        f"/api/v1/pedimentos/{ped_id}/partidas/{p1['id']}", headers=headers, json={"clave_prodserv": "11111600"}
    )
    assert res.status_code == 200 and res.json()["clave_prodserv"] == "11111600"

    # Aplicar sin almacén → 404
    assert (
        client.post(f"/api/v1/pedimentos/{ped_id}/aplicar-inventario", headers=headers, json={"codigo_almacen": "NOPE"}).status_code
        == 404
    )
    client.post("/api/v1/inventory/almacenes", headers=headers, json={"nombre": "Bodega CDMX", "codigo": "CDMX"})

    res = client.post(f"/api/v1/pedimentos/{ped_id}/aplicar-inventario", headers=headers, json={"codigo_almacen": "CDMX"})
    assert res.status_code == 200, res.text
    out = res.json()
    assert out["movimientos_creados"] == 19
    # Ninguna partida existía en el catálogo; el M3 trae 2 descripciones repetidas
    # ("ARTICULOS DE USO DOMESTICO" y "MANUFACTURAS DE PLASTICO", con fracción
    # distinta) que entran al MISMO producto → 19 partidas, 17 productos.
    assert out["productos_creados"] == 17
    assert out["costo_total"] == pytest.approx(ped["resumen"]["costo_total"], abs=0.01)

    # Quedó congelado
    detalle = client.get(f"/api/v1/pedimentos/{ped_id}", headers=headers).json()
    assert detalle["estatus"] == "aplicado"
    assert all(p["producto_id"] for p in detalle["partidas"])
    assert client.patch(f"/api/v1/pedimentos/{ped_id}", headers=headers, json={"utilidad": 1}).status_code == 409
    assert client.delete(f"/api/v1/pedimentos/{ped_id}", headers=headers).status_code == 409
    assert (
        client.post(f"/api/v1/pedimentos/{ped_id}/aplicar-inventario", headers=headers, json={"codigo_almacen": "CDMX"}).status_code
        == 409
    )

    # Y el inventario refleja las entradas con costo y referencia al pedimento
    stock = client.get("/api/v1/inventory/stock", headers=headers).json()
    piedras = next(s for s in stock if s["nombre_producto"] == "PIEDRAS DECORATIVAS")
    assert piedras["disponible"] == 2976 and piedras["codigo_almacen"] == "CDMX"
    movs = client.get("/api/v1/inventory/movimientos?limit=50", headers=headers).json()
    assert len(movs) == 19
    assert all(m["referencia"] == "PED 26 51 3382 6000018" and m["tipo"] == "entrada" for m in movs)
    m_piedras = next(m for m in movs if m["nombre_producto"] == "PIEDRAS DECORATIVAS")
    assert m_piedras["costo_unitario"] == pytest.approx(p1["costeo"]["costo_unitario"], abs=1e-6)
    productos = client.get("/api/v1/inventory/productos", headers=headers).json()
    prod_piedras = next(p for p in productos if p["nombre"] == "PIEDRAS DECORATIVAS")
    assert prod_piedras["clave_prodserv"] == "11111600"
    assert prod_piedras["unidad_codigo"] == "H87"
    assert prod_piedras["categoria"] == "Importación"


def test_partidas_se_ligan_a_productos_existentes_por_nombre(client, seed_rbac, db):
    usuario, empresa = _empresa_admin(db, seed_rbac)
    headers = auth_headers(client, email=usuario.email, password="Demo1234!", empresa_id=empresa.id)
    client.post(
        "/api/v1/inventory/productos",
        headers=headers,
        json={"sku": "PIEDRA-01", "nombre": "Piedras decorativas", "costo_unitario": 1, "atributos": None},
    )
    ped = _importar(client, headers).json()["pedimento"]
    p1 = ped["partidas"][0]
    assert p1["producto_sku"] == "PIEDRA-01"  # match case-insensitive por nombre
    assert sum(1 for p in ped["partidas"] if p["producto_id"]) == 1


def test_captura_manual_de_pedimento(client, seed_rbac, db):
    usuario, empresa = _empresa_admin(db, seed_rbac)
    headers = auth_headers(client, email=usuario.email, password="Demo1234!", empresa_id=empresa.id)
    res = client.post(
        "/api/v1/pedimentos",
        headers=headers,
        json={
            "numero": "6000024",
            "patente": "3382",
            "aduana": "160",
            "clave_pedimento": "A1",
            "fecha_pago": "2026-02-10",
            "tipo_cambio": "17.8905",
            "dta": 2880,
            "utilidad": 500,
            "partidas": [
                {"secuencia": 1, "fraccion": "64039999", "descripcion": "CALZADO", "cantidad_umc": 490, "umc_clave": "9", "precio_unitario": "674.11429", "valor_aduana": 330316, "igi": 115611, "iva": 71771},
                {"secuencia": 2, "fraccion": "64069090", "descripcion": "HORMAS PARA CALZADO", "cantidad_umc": 7634, "umc_clave": "6", "precio_unitario": "1.61017", "valor_aduana": 12292, "igi": 3073, "iva": 2474},
                {"secuencia": 3, "fraccion": "64069090", "descripcion": "PLANTILLAS", "cantidad_umc": 6418, "umc_clave": "6", "precio_unitario": "1.78903", "valor_aduana": 11482, "igi": 1148, "iva": 2035},
                {"secuencia": 4, "fraccion": "64062000", "descripcion": "SUELAS", "cantidad_umc": 5458, "umc_clave": "9", "precio_unitario": "1.07347", "valor_aduana": 5859, "igi": 293, "iva": 992},
            ],
        },
    )
    assert res.status_code == 201, res.text
    ped = res.json()
    assert ped["origen"] == "manual"
    assert ped["numero_completo"] == "26 16 3382 6000024"
    # Fila 3 del Excel: AC = 911.7795961 (J + S + U + AA)
    assert ped["partidas"][0]["costeo"]["precio_unitario_venta"] == pytest.approx(911.7796, abs=0.001)
    assert ped["partidas"][0]["clave_unidad_sat"] == "PR"
    assert ped["partidas"][0]["valor_usd"] == pytest.approx(330316 / 17.8905, abs=0.01)


def test_contador_de_otra_empresa_no_ve_pedimentos(client, seed_rbac, db):
    usuario, empresa = _empresa_admin(db, seed_rbac)
    headers = auth_headers(client, email=usuario.email, password="Demo1234!", empresa_id=empresa.id)
    ped_id = _importar(client, headers).json()["pedimento"]["id"]

    otro = crear_usuario(db)
    otra_empresa = crear_empresa(db)
    agregar_membresia(db, usuario=otro, empresa=otra_empresa, rol=seed_rbac["contador"])
    headers_otro = auth_headers(client, email=otro.email, password="Demo1234!", empresa_id=otra_empresa.id)
    assert client.get("/api/v1/pedimentos", headers=headers_otro).json() == []
    assert client.get(f"/api/v1/pedimentos/{ped_id}", headers=headers_otro).status_code == 404
