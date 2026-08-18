"""Clientes y proveedores: detección desde la bóveda, cifras (facturado, saldo,
antigüedad), CRUD, EFOS y carga masiva."""

import io

import openpyxl

from app.modules.sat.mock_generator import generar_cfdis_mock
from tests.conftest import agregar_membresia, auth_headers, crear_empresa, crear_usuario
from tests.test_xml_cfdi import EMPRESA, XML_GASTO, XML_PPD, XML_PUE, XML_REP


def _setup(client, db, seed_rbac, rfc=None, mock=True):
    usuario = crear_usuario(db)
    empresa = crear_empresa(db, rfc=rfc, razon_social="Nubinox Demo")
    agregar_membresia(db, usuario=usuario, empresa=empresa, rol=seed_rbac["administrador"])
    cfdis = generar_cfdis_mock(db, empresa=empresa, cantidad=80, dias_atras=200, seed=21) if mock else []
    return auth_headers(client, email=usuario.email, password="Demo1234!", empresa_id=empresa.id), empresa, cfdis


def test_sincronizar_desde_cfdi_y_lista(client, seed_rbac, db):
    headers, empresa, cfdis = _setup(client, db, seed_rbac)
    assert client.get("/api/v1/terceros", headers=headers).json() == []
    r = client.post("/api/v1/terceros/sincronizar", headers=headers).json()
    clientes_rfc = {c.rfc_receptor for c in cfdis if c.direccion == "emitido" and c.tipo != "nomina"}
    prov_rfc = {c.rfc_emisor for c in cfdis if c.direccion == "recibido"}
    assert r["creados"] == len(clientes_rfc | prov_rfc) and r["total"] == r["creados"]
    # Empleados de nómina NO se vuelven clientes
    empleados = {c.rfc_receptor for c in cfdis if c.tipo == "nomina"}
    lista = client.get("/api/v1/terceros", headers=headers).json()
    assert not ({t["rfc"] for t in lista} & empleados)
    # Los EFOS del mock quedan marcados
    efos = [t for t in lista if t["es_efos"]]
    if any(c.rfc_emisor.startswith("EFO") or c.rfc_receptor.startswith("EFO") for c in cfdis):
        assert efos
    # Filtro por tipo: "ambos" aparece en los dos
    cli = client.get("/api/v1/terceros?tipo=cliente", headers=headers).json()
    prov = client.get("/api/v1/terceros?tipo=proveedor", headers=headers).json()
    assert all(t["tipo"] in ("cliente", "ambos") for t in cli) and all(t["tipo"] in ("proveedor", "ambos") for t in prov)
    # Cifras: num_cfdis y último CFDI coinciden con la bóveda
    uno = cli[0]
    esperado = [c for c in cfdis if uno["rfc"] in (c.rfc_receptor, c.rfc_emisor) and c.tipo != "nomina"]
    assert uno["num_cfdis"] == len(esperado)
    assert uno["ultimo_cfdi"] == max(c.fecha for c in esperado).isoformat()
    # Idempotente
    r2 = client.post("/api/v1/terceros/sincronizar", headers=headers).json()
    assert r2["creados"] == 0


def test_saldos_y_antiguedad_con_xml_reales(client, seed_rbac, db):
    headers, empresa, _ = _setup(client, db, seed_rbac, rfc=EMPRESA, mock=False)
    zipf = io.BytesIO()
    import zipfile

    with zipfile.ZipFile(zipf, "w") as z:
        for n, c in {"pue.xml": XML_PUE, "ppd.xml": XML_PPD, "rep.xml": XML_REP, "gasto.xml": XML_GASTO}.items():
            z.writestr(n, c)
    client.post("/api/v1/sat/cargar-xml", headers=headers, files=[("archivos", ("z.zip", zipf.getvalue(), "application/zip"))])
    client.post("/api/v1/terceros/sincronizar", headers=headers)
    lista = client.get("/api/v1/terceros", headers=headers).json()
    cli = next(t for t in lista if t["rfc"] == "CLI900101AA1")
    prov = next(t for t in lista if t["rfc"] == "PRO850505BB2")
    assert cli["tipo"] == "cliente" and cli["nombre"] == "Cliente Uno" and cli["origen"] == "cfdi"
    assert prov["tipo"] == "proveedor"
    # Cliente: PPD 23,200 − REP 11,600 = 11,600 pendiente
    assert cli["saldo_pendiente"] == 11600 and cli["num_cfdis"] == 3
    det = client.get(f"/api/v1/terceros/{cli['id']}", headers=headers).json()
    assert det["por_cobrar"]["total"] == 11600 and det["por_cobrar"]["num_cfdis"] == 1
    assert det["por_pagar"]["total"] == 0
    assert det["total_emitido"] == 11600 + 23200
    assert prov["saldo_pendiente"] == 0


def test_crud_manual_y_carga_excel(client, seed_rbac, db):
    headers, empresa, _ = _setup(client, db, seed_rbac, mock=False)
    res = client.post("/api/v1/terceros", headers=headers, json={"rfc": "abc010101xyz", "nombre": "Nuevo Cliente", "tipo": "cliente", "email": "a@b.mx", "dias_credito": 30, "limite_credito": 50000})
    assert res.status_code == 201, res.text
    t = res.json()
    assert t["rfc"] == "ABC010101XYZ" and t["dias_credito"] == 30 and t["limite_credito"] == 50000
    assert client.post("/api/v1/terceros", headers=headers, json={"rfc": "ABC010101XYZ", "nombre": "Dup"}).status_code == 409
    assert client.post("/api/v1/terceros", headers=headers, json={"rfc": "ABC010101XYZ", "nombre": "x", "tipo": "raro"}).status_code == 422
    upd = client.patch(f"/api/v1/terceros/{t['id']}", headers=headers, json={"telefono": "5512345678", "tipo": "ambos", "activo": False}).json()
    assert upd["telefono"] == "5512345678" and upd["tipo"] == "ambos" and upd["activo"] is False

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["RFC", "Razón social", "Tipo", "Correo", "Teléfono", "Días crédito", "CP"])
    ws.append(["ABC010101XYZ", "Nuevo Cliente SA", "cliente", "pagos@nc.mx", "555", 45, 6600])
    ws.append(["PRO850505BB2", "Proveedor SA", "proveedor", None, None, None, None])
    ws.append(["MAL", "RFC corto", "cliente", None, None, None, None])
    ws.append(["PRO850505BB2", "Repetido", "proveedor", None, None, None, None])
    buf = io.BytesIO()
    wb.save(buf)
    r = client.post("/api/v1/terceros/importar", headers=headers, files={"archivo": ("t.xlsx", buf.getvalue(), "application/octet-stream")}).json()
    assert (r["creados"], r["actualizados"]) == (1, 1) and {e["fila"] for e in r["errores"]} == {4, 5}
    lista = client.get("/api/v1/terceros?activo=false", headers=headers).json()
    nc = next(x for x in lista if x["rfc"] == "ABC010101XYZ")
    assert nc["dias_credito"] == 45 and nc["codigo_postal"] == "6600" and nc["email"] == "pagos@nc.mx"
    assert client.get("/api/v1/terceros/plantilla", headers=headers).status_code == 200
