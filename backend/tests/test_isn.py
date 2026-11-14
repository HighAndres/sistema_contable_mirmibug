"""ISN (Impuesto Sobre Nóminas): base por entidad federativa y tasa estatal."""

import uuid
from datetime import date
from decimal import Decimal

from app.modules.cfdi.models import Cfdi, CfdiNomina
from tests.conftest import agregar_membresia, auth_headers, crear_empresa, crear_usuario


def _setup(client, db, seed_rbac):
    usuario = crear_usuario(db)
    empresa = crear_empresa(db)
    agregar_membresia(db, usuario=usuario, empresa=empresa, rol=seed_rbac["administrador"])
    headers = auth_headers(client, email=usuario.email, password="Demo1234!", empresa_id=empresa.id)
    return headers, empresa


def _recibo(db, empresa, *, entidad, percepciones, fecha=date(2026, 3, 14), fecha_pago=date(2026, 3, 15), con_complemento=True, estatus="vigente"):
    c = Cfdi(
        empresa_id=empresa.id,
        uuid_fiscal=str(uuid.uuid4()).upper(),
        tipo="nomina",
        direccion="emitido",
        rfc_emisor=empresa.rfc,
        nombre_emisor=empresa.razon_social,
        rfc_receptor="XEXX010101000",
        nombre_receptor="Empleado de Prueba",
        subtotal=Decimal(percepciones),
        iva=Decimal("0"),
        total=Decimal(percepciones),
        fecha=fecha,
        estatus=estatus,
    )
    db.add(c)
    db.flush()
    if con_complemento:
        db.add(
            CfdiNomina(
                cfdi_id=c.id,
                fecha_pago=fecha_pago,
                total_percepciones=Decimal(percepciones),
                total_deducciones=Decimal("0"),
                total_otros_pagos=Decimal("0"),
                clave_ent_fed=entidad,
            )
        )
    db.commit()
    return c


def test_isn_agrupa_por_entidad_y_aplica_su_tasa(client, seed_rbac, db):
    headers, empresa = _setup(client, db, seed_rbac)
    _recibo(db, empresa, entidad="JAL", percepciones="10000.00")
    _recibo(db, empresa, entidad="JAL", percepciones="5000.00")
    _recibo(db, empresa, entidad="CMX", percepciones="20000.00")
    _recibo(db, empresa, entidad="DIF", percepciones="1000.00")  # clave vieja de CDMX: se normaliza
    _recibo(db, empresa, entidad="JAL", percepciones="999.00", estatus="cancelado")  # fuera

    b = client.get("/api/v1/impuestos/isn?anio=2026&mes=3", headers=headers).json()
    filas = {f["entidad_codigo"]: f for f in b["filas"]}
    assert set(filas) == {"JAL", "CMX"}
    assert filas["JAL"]["recibos"] == 2 and filas["JAL"]["base"] == 15000
    assert filas["JAL"]["tasa"] == 0.03 and filas["JAL"]["isn"] == 450
    assert filas["CMX"]["base"] == 21000 and filas["CMX"]["entidad_nombre"] == "Ciudad de México"
    assert filas["CMX"]["isn"] == 840  # 4%
    assert b["total_base"] == 36000 and b["total_isn"] == 1290


def test_isn_usa_la_fecha_de_pago_y_reporta_sin_complemento(client, seed_rbac, db):
    headers, empresa = _setup(client, db, seed_rbac)
    # Emitido en marzo pero PAGADO en abril: cae en abril.
    _recibo(db, empresa, entidad="JAL", percepciones="10000.00", fecha=date(2026, 3, 31), fecha_pago=date(2026, 4, 1))
    # Sin complemento de nómina: no se le puede calcular ISN y se advierte.
    _recibo(db, empresa, entidad=None, percepciones="7000.00", fecha=date(2026, 4, 10), con_complemento=False)

    marzo = client.get("/api/v1/impuestos/isn?anio=2026&mes=3", headers=headers).json()
    assert marzo["filas"] == [] and marzo["total_isn"] == 0

    abril = client.get("/api/v1/impuestos/isn?anio=2026&mes=4", headers=headers).json()
    assert abril["total_base"] == 10000
    assert any("sin complemento" in a for a in abril["advertencias"])
    assert abril["anios_disponibles"] == [2026]


def test_isn_requiere_permiso(client, seed_rbac, db):
    from app.modules.auth.models import Rol

    usuario = crear_usuario(db)
    empresa = crear_empresa(db)
    rol = Rol(nombre="solo-cfdi", es_sistema=False, permisos=[seed_rbac["permisos"]["cfdi.leer"]])
    db.add(rol)
    db.commit()
    agregar_membresia(db, usuario=usuario, empresa=empresa, rol=rol)
    headers = auth_headers(client, email=usuario.email, password="Demo1234!", empresa_id=empresa.id)
    assert client.get("/api/v1/impuestos/isn?anio=2026", headers=headers).status_code == 403
