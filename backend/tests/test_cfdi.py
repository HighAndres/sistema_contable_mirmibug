"""Lista de CFDI: filtros (tipo, estatus, emisor/receptor, mes/año, método y forma
de pago, UUID, búsqueda libre), resumen por tipo y datos nuevos (serie/folio/método)."""

from datetime import date

from app.modules.sat.mock_generator import generar_cfdis_mock
from tests.conftest import agregar_membresia, auth_headers, crear_empresa, crear_usuario


def _setup(client, db, seed_rbac, cantidad=120):
    usuario = crear_usuario(db)
    empresa = crear_empresa(db)
    agregar_membresia(db, usuario=usuario, empresa=empresa, rol=seed_rbac["administrador"])
    cfdis = generar_cfdis_mock(db, empresa=empresa, cantidad=cantidad, dias_atras=200, seed=11)
    headers = auth_headers(client, email=usuario.email, password="Demo1234!", empresa_id=empresa.id)
    return headers, cfdis


def test_mock_genera_serie_folio_metodo_y_nomina(client, seed_rbac, db):
    headers, cfdis = _setup(client, db, seed_rbac)
    tipos = {c.tipo for c in cfdis}
    assert {"ingreso", "egreso", "pago", "nomina"} <= tipos
    assert all(c.version == "4.0" and c.folio for c in cfdis)
    for c in cfdis:
        if c.tipo in ("ingreso", "egreso"):
            assert c.metodo_pago_codigo == ("PPD" if c.forma_pago_codigo == "99" else "PUE")
        else:
            assert c.metodo_pago_codigo is None
        if c.tipo == "nomina":
            assert c.direccion == "emitido" and c.iva == 0 and c.serie == "N"
    # Folios consecutivos por dirección, sin repetir
    emitidos = sorted(int(c.folio) for c in cfdis if c.direccion == "emitido")
    assert emitidos == list(range(1, len(emitidos) + 1))


def test_filtros_de_lista(client, seed_rbac, db):
    headers, cfdis = _setup(client, db, seed_rbac)

    def listar(**params):
        qs = "&".join(f"{k}={v}" for k, v in params.items())
        res = client.get(f"/api/v1/cfdi?limit=500&{qs}", headers=headers)
        assert res.status_code == 200, res.text
        return res.json()

    assert listar()["total"] == len(cfdis)
    assert listar(tipo="nomina")["total"] == sum(1 for c in cfdis if c.tipo == "nomina")
    assert listar(estatus="cancelado")["total"] == sum(1 for c in cfdis if c.estatus == "cancelado")
    assert listar(metodo_pago="PPD")["total"] == sum(1 for c in cfdis if c.metodo_pago_codigo == "PPD")
    assert listar(forma_pago="03")["total"] == sum(1 for c in cfdis if c.forma_pago_codigo == "03")

    algun_mes = cfdis[0].fecha
    esperado = sum(1 for c in cfdis if c.fecha.year == algun_mes.year and c.fecha.month == algun_mes.month)
    assert listar(anio=algun_mes.year, mes=algun_mes.month)["total"] == esperado

    # Emisor / receptor por RFC o nombre (contiene, sin distinguir mayúsculas)
    recibido = next(c for c in cfdis if c.direccion == "recibido")
    assert listar(emisor=recibido.rfc_emisor.lower())["total"] == sum(1 for c in cfdis if c.rfc_emisor == recibido.rfc_emisor)
    assert listar(receptor="peninsular")["total"] == sum(1 for c in cfdis if "Peninsular" in c.nombre_receptor)

    # UUID exacto y parcial, y búsqueda libre por folio
    uno = cfdis[5]
    assert [i["id"] for i in listar(uuid_fiscal=uno.uuid_fiscal)["items"]] == [str(uno.id)]
    assert listar(uuid_fiscal=uno.uuid_fiscal[:8])["total"] >= 1
    assert any(i["id"] == str(uno.id) for i in listar(q=uno.uuid_fiscal[-12:])["items"])

    # Los campos nuevos viajan en la respuesta
    item = listar(uuid_fiscal=uno.uuid_fiscal)["items"][0]
    assert item["serie"] == uno.serie and item["folio"] == uno.folio and item["version"] == "4.0"
    assert item["metodo_pago_codigo"] == uno.metodo_pago_codigo

    # Filtro inválido → 422
    assert client.get("/api/v1/cfdi?estatus=raro", headers=headers).status_code == 422


def test_resumen_por_tipo(client, seed_rbac, db):
    headers, cfdis = _setup(client, db, seed_rbac)
    res = client.get("/api/v1/cfdi/resumen", headers=headers)
    assert res.status_code == 200, res.text
    r = res.json()
    for tipo in ("ingreso", "egreso", "pago", "nomina"):
        del_tipo = [c for c in cfdis if c.tipo == tipo]
        assert r[tipo]["cantidad"] == len(del_tipo)
        assert r[tipo]["cancelados"] == sum(1 for c in del_tipo if c.estatus == "cancelado")
        assert abs(r[tipo]["total"] - float(sum(c.total for c in del_tipo if c.estatus != "cancelado"))) < 0.01
    assert r["ingreso"]["ppd"] == sum(1 for c in cfdis if c.tipo == "ingreso" and c.metodo_pago_codigo == "PPD" and c.estatus != "cancelado")
    assert date.today().year in r["anios"]

    # El resumen respeta los demás filtros pero ignora `tipo` (las 4 tarjetas siempre)
    r2 = client.get("/api/v1/cfdi/resumen?tipo=nomina&estatus=vigente", headers=headers).json()
    assert r2["ingreso"]["cantidad"] == sum(1 for c in cfdis if c.tipo == "ingreso" and c.estatus == "vigente")
