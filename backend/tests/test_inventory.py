"""Pruebas del ledger de inventario: alta de producto con atributos libres,
movimientos, y el bloqueo de stock negativo."""

from tests.conftest import agregar_membresia, auth_headers, crear_empresa, crear_usuario


def _empresa_con_admin(db, seed_rbac):
    usuario = crear_usuario(db)
    empresa = crear_empresa(db)
    agregar_membresia(db, usuario=usuario, empresa=empresa, rol=seed_rbac["administrador"])
    headers_sin_empresa = {"email": usuario.email, "password": "Demo1234!"}
    return usuario, empresa, headers_sin_empresa


def test_crear_producto_con_categoria_tipo_y_atributos(client, seed_rbac, db):
    usuario, empresa, creds = _empresa_con_admin(db, seed_rbac)
    headers = auth_headers(client, email=creds["email"], password=creds["password"], empresa_id=empresa.id)

    res = client.post(
        "/api/v1/inventory/productos",
        headers=headers,
        json={
            "sku": "BIC-001",
            "nombre": "Bicicleta de reparto",
            "categoria": "Logística",
            "tipo": "producto",
            "costo_unitario": 4500,
            "atributos": {"rodada": "26 pulgadas", "color": "rojo"},
        },
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["categoria"] == "Logística"
    assert body["atributos"] == {"rodada": "26 pulgadas", "color": "rojo"}

    servicio = client.post(
        "/api/v1/inventory/productos",
        headers=headers,
        json={"sku": "SRV-999", "nombre": "Soporte técnico", "tipo": "servicio", "categoria": "Servicios"},
    )
    assert servicio.status_code == 201
    assert servicio.json()["tipo"] == "servicio"

    categorias = client.get("/api/v1/inventory/categorias", headers=headers).json()
    assert set(categorias) == {"Logística", "Servicios"}


def test_movimientos_entrada_salida_y_stock_actual(client, seed_rbac, db):
    usuario, empresa, creds = _empresa_con_admin(db, seed_rbac)
    headers = auth_headers(client, email=creds["email"], password=creds["password"], empresa_id=empresa.id)

    client.post("/api/v1/inventory/almacenes", headers=headers, json={"nombre": "Central", "codigo": "CENTRAL"})
    client.post(
        "/api/v1/inventory/productos",
        headers=headers,
        json={"sku": "PROD-1", "nombre": "Producto de prueba", "costo_unitario": 100},
    )

    entrada = client.post(
        "/api/v1/inventory/movimientos",
        headers=headers,
        json={"sku": "PROD-1", "codigo_almacen": "CENTRAL", "tipo": "entrada", "cantidad": 10},
    )
    assert entrada.status_code == 201

    salida = client.post(
        "/api/v1/inventory/movimientos",
        headers=headers,
        json={"sku": "PROD-1", "codigo_almacen": "CENTRAL", "tipo": "salida", "cantidad": -4},
    )
    assert salida.status_code == 201

    stock = client.get("/api/v1/inventory/stock", headers=headers).json()
    assert len(stock) == 1
    assert stock[0]["disponible"] == 6


def test_stock_insuficiente_devuelve_409(client, seed_rbac, db):
    usuario, empresa, creds = _empresa_con_admin(db, seed_rbac)
    headers = auth_headers(client, email=creds["email"], password=creds["password"], empresa_id=empresa.id)

    client.post("/api/v1/inventory/almacenes", headers=headers, json={"nombre": "Central", "codigo": "CENTRAL"})
    client.post(
        "/api/v1/inventory/productos", headers=headers, json={"sku": "PROD-2", "nombre": "Producto escaso"}
    )
    client.post(
        "/api/v1/inventory/movimientos",
        headers=headers,
        json={"sku": "PROD-2", "codigo_almacen": "CENTRAL", "tipo": "entrada", "cantidad": 3},
    )

    res = client.post(
        "/api/v1/inventory/movimientos",
        headers=headers,
        json={"sku": "PROD-2", "codigo_almacen": "CENTRAL", "tipo": "salida", "cantidad": -5},
    )
    assert res.status_code == 409


def test_contador_no_puede_gestionar_credenciales_sat(client, seed_rbac, db):
    """RBAC por empresa: un rol contador no debe tener permisos de administrador."""
    usuario = crear_usuario(db, email="contador_test@test.nubinox")
    empresa = crear_empresa(db)
    agregar_membresia(db, usuario=usuario, empresa=empresa, rol=seed_rbac["contador"])
    headers = auth_headers(client, email=usuario.email, password="Demo1234!", empresa_id=empresa.id)

    res = client.post(
        "/api/v1/credentials/conectar", headers=headers, json={"tipo": "ciec"}
    )
    assert res.status_code == 403

    # Pero sí puede leer y ajustar inventario.
    res_stock = client.get("/api/v1/inventory/stock", headers=headers)
    assert res_stock.status_code == 200
