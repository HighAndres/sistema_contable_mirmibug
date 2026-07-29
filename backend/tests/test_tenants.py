"""Pruebas de tenants: creación de empresa, aislamiento multi-tenant,
invitación de usuarios (incluye el hallazgo de seguridad ya corregido) y el
acceso "a todas las empresas" del superadmin."""

from tests.conftest import agregar_membresia, auth_headers, crear_empresa, crear_usuario


def test_crear_empresa_hace_al_creador_administrador(client, seed_rbac, db):
    usuario = crear_usuario(db, email="fundador@test.nubinox")
    headers = auth_headers(client, email=usuario.email, password="Demo1234!")

    res = client.post(
        "/api/v1/tenants/empresas",
        headers=headers,
        json={"rfc": "FUN010101AB1", "razon_social": "Fundador SA de CV"},
    )
    assert res.status_code == 201, res.text
    empresa_id = res.json()["id"]

    mias = client.get("/api/v1/tenants/empresas/mias", headers=headers)
    assert mias.status_code == 200
    membresias = mias.json()
    assert len(membresias) == 1
    assert membresias[0]["empresa"]["id"] == empresa_id
    assert membresias[0]["rol"] == "administrador"
    assert "cfdi.leer" in membresias[0]["permisos"]


def test_usuario_sin_membresia_no_accede_a_otra_empresa(client, seed_rbac, db):
    """Aislamiento multi-tenant: X-Empresa-Id de una empresa ajena debe rechazarse."""
    _u1, empresa_ajena, _p1 = _empresa_con_admin(db, seed_rbac)
    intruso = crear_usuario(db, email="intruso@test.nubinox")
    headers = auth_headers(client, email=intruso.email, password="Demo1234!", empresa_id=empresa_ajena.id)

    res = client.get("/api/v1/cfdi", headers=headers)
    assert res.status_code == 403


def _empresa_con_admin(db, seed_rbac):
    usuario = crear_usuario(db)
    empresa = crear_empresa(db)
    agregar_membresia(db, usuario=usuario, empresa=empresa, rol=seed_rbac["administrador"])
    return usuario, empresa, "Demo1234!"


def test_invitar_usuario_nuevo_crea_cuenta_y_membresia(client, seed_rbac, db):
    usuario, empresa, password = _empresa_con_admin(db, seed_rbac)
    headers = auth_headers(client, email=usuario.email, password=password, empresa_id=empresa.id)

    res = client.post(
        "/api/v1/tenants/usuarios/invitar",
        headers=headers,
        json={"email": "colega@test.nubinox", "rol_nombre": "contador"},
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["usuario_nuevo"] is True
    assert body["password_temporal"] is not None

    miembros = client.get("/api/v1/tenants/usuarios", headers=headers).json()
    correos = {m["email"] for m in miembros}
    assert "colega@test.nubinox" in correos


def test_invitar_usuario_ya_existente_es_rechazado(client, seed_rbac, db):
    """Hallazgo de seguridad: no se debe poder unir a un correo ya registrado
    a otra empresa sin su consentimiento (evita membresías no autorizadas y
    el oráculo de existencia de cuentas)."""
    usuario, empresa, password = _empresa_con_admin(db, seed_rbac)
    crear_usuario(db, email="ya.registrado@test.nubinox")
    headers = auth_headers(client, email=usuario.email, password=password, empresa_id=empresa.id)

    res = client.post(
        "/api/v1/tenants/usuarios/invitar",
        headers=headers,
        json={"email": "ya.registrado@test.nubinox", "rol_nombre": "contador"},
    )
    assert res.status_code == 400


def test_superadmin_ve_todas_las_empresas(client, seed_rbac, db):
    _u1, empresa1, _p1 = _empresa_con_admin(db, seed_rbac)
    _u2, empresa2, _p2 = _empresa_con_admin(db, seed_rbac)
    superadmin = crear_usuario(db, email="jefe@test.nubinox", is_superadmin=True)

    headers = auth_headers(client, email=superadmin.email, password="Demo1234!")
    mias = client.get("/api/v1/tenants/empresas/mias", headers=headers).json()
    ids = {m["empresa"]["id"] for m in mias}
    assert str(empresa1.id) in ids
    assert str(empresa2.id) in ids
    assert all(m["rol"] == "superadmin" for m in mias)

    # Y puede operar sobre cualquiera de ellas sin tener una membresía real.
    headers_empresa1 = {**headers, "X-Empresa-Id": str(empresa1.id)}
    res = client.get("/api/v1/cfdi", headers=headers_empresa1)
    assert res.status_code == 200
