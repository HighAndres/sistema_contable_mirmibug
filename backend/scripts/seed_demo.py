"""Seed de datos completos para la demo: empresa, usuarios, CFDIs e inventario.

Pensado para correr sobre una base recién migrada y con seed_rbac.py +
seed_catalogs.py ya aplicados:

    PYTHONPATH=. python scripts/create_db.py
    PYTHONPATH=. alembic upgrade head
    PYTHONPATH=. python scripts/seed_rbac.py
    PYTHONPATH=. python scripts/seed_catalogs.py
    PYTHONPATH=. python scripts/seed_demo.py

Es tolerante a re-ejecuciones (reutiliza usuario/empresa si ya existen), pero
para una demo predecible lo ideal es correrlo sobre una base limpia.
"""

import random
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.modules.auth.models import Rol, Usuario
from app.modules.cfdi.models import Cfdi
from app.modules.credentials import crud as credenciales_crud
from app.modules.inventory import crud as inventory_crud
from app.modules.rules import crud as rules_crud
from app.modules.sat.mock_generator import generar_cfdis_mock
from app.modules.tenants.models import Empresa, UsuarioEmpresa

ADMIN_EMAIL = "admin@nubinox.demo"
CONTADOR_EMAIL = "contador@nubinox.demo"
SUPERADMIN_EMAIL = "superadmin@nubinox.demo"
DEMO_PASSWORD = "Demo1234!"

EMPRESA_RFC = "NUB010101ABC"
EMPRESA_RAZON_SOCIAL = "Nubinox Demo SA de CV"

# (sku, nombre, tipo, categoria, unidad_codigo, costo, atributos)
# "categoria" es texto libre (cada empresa define las suyas) y "atributos" es
# JSON arbitrario — así el mismo modelo de Producto sirve para cualquier giro,
# no solo cómputo/oficina como en este seed.
PRODUCTOS_SEED = [
    ("LAP-001", "Laptop 14 pulgadas i5", "producto", "Cómputo", "H87", 12000, {"color": "gris espacial", "ram_gb": 16}),
    ("LAP-002", "Laptop 15 pulgadas i7", "producto", "Cómputo", "H87", 18500, {"color": "negro", "ram_gb": 32}),
    ("MON-001", "Monitor 24 pulgadas Full HD", "producto", "Cómputo", "H87", 2800, {"pulgadas": 24}),
    ("MON-002", "Monitor 27 pulgadas 4K", "producto", "Cómputo", "H87", 5200, {"pulgadas": 27}),
    ("TEC-001", "Teclado mecánico USB", "producto", "Cómputo", "H87", 650, None),
    ("MOU-001", "Mouse inalámbrico", "producto", "Cómputo", "H87", 320, None),
    ("SIL-001", "Silla ergonómica de oficina", "producto", "Mobiliario", "H87", 3200, {"color": "negro"}),
    ("ESC-001", "Escritorio ejecutivo 120cm", "producto", "Mobiliario", "H87", 4100, {"material": "melamina"}),
    ("ARC-001", "Archivero metálico 4 gavetas", "producto", "Mobiliario", "H87", 3900, None),
    ("IMP-001", "Impresora multifuncional láser", "producto", "Oficina", "H87", 5600, None),
    ("TON-001", "Tóner negro compatible", "producto", "Oficina", "H87", 480, None),
    ("PAP-001", "Papel bond carta (caja 5000 hojas)", "producto", "Oficina", "H87", 850, None),
    ("PRO-001", "Proyector portátil HD", "producto", "Audiovisual", "H87", 7200, {"lumens": 3200}),
    ("CAM-001", "Cámara web full HD", "producto", "Audiovisual", "H87", 890, None),
    ("AUD-001", "Diadema con micrófono USB", "producto", "Audiovisual", "H87", 540, None),
    ("UPS-001", "No-break 600VA", "producto", "Redes y energía", "H87", 1100, None),
    ("SWI-001", "Switch de red 8 puertos", "producto", "Redes y energía", "H87", 780, None),
    ("CAB-001", "Cable de red Cat6 (rollo 305m)", "producto", "Redes y energía", "H87", 1450, None),
    ("DIS-001", "Disco duro externo 2TB", "producto", "Cómputo", "H87", 1650, {"capacidad_tb": 2}),
    ("MEM-001", "Memoria USB 64GB", "producto", "Cómputo", "H87", 280, {"capacidad_gb": 64}),
    # Servicio: mismo catálogo, sin control de existencias (no genera movimientos de stock).
    ("SRV-001", "Consultoría fiscal mensual", "servicio", "Consultoría", "E48", 3500, {"recurrente": True}),
]

ALMACENES_SEED = [
    ("Almacén Central", "CENTRAL"),
    ("Sucursal Norte", "NORTE"),
]


def get_or_create_usuario(
    db: Session, *, email: str, password: str, nombre: str, is_superadmin: bool = False
) -> Usuario:
    user = db.scalar(select(Usuario).where(Usuario.email == email))
    if user is None:
        user = Usuario(
            email=email,
            hashed_password=hash_password(password),
            nombre_completo=nombre,
            is_superadmin=is_superadmin,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


def ensure_membership(db: Session, *, usuario: Usuario, empresa: Empresa, rol_nombre: str) -> None:
    existente = db.scalar(
        select(UsuarioEmpresa).where(
            UsuarioEmpresa.usuario_id == usuario.id, UsuarioEmpresa.empresa_id == empresa.id
        )
    )
    if existente is not None:
        return
    rol = db.scalar(select(Rol).where(Rol.nombre == rol_nombre))
    if rol is None:
        raise RuntimeError(f"Rol '{rol_nombre}' no existe: corre scripts/seed_rbac.py primero")
    db.add(UsuarioEmpresa(usuario_id=usuario.id, empresa_id=empresa.id, rol_id=rol.id))
    db.commit()


def seed_inventario(db: Session, *, empresa: Empresa, rng: random.Random) -> None:
    almacenes = []
    for nombre, codigo in ALMACENES_SEED:
        almacen = inventory_crud.get_almacen_por_codigo(db, empresa_id=empresa.id, codigo=codigo)
        if almacen is None:
            almacen = inventory_crud.crear_almacen(db, empresa_id=empresa.id, nombre=nombre, codigo=codigo)
        almacenes.append(almacen)

    for sku, nombre, tipo, categoria, unidad, costo, atributos in PRODUCTOS_SEED:
        producto = inventory_crud.get_producto_por_sku(db, empresa_id=empresa.id, sku=sku)
        if producto is not None:
            # Ya sembrado en una corrida previa (posiblemente antes de que
            # existieran tipo/categoria/atributos): refresca los metadatos,
            # sin tocar el historial de movimientos ya generado.
            producto.tipo = tipo
            producto.categoria = categoria
            producto.atributos = atributos
            db.commit()
            continue
        producto = inventory_crud.crear_producto(
            db,
            empresa_id=empresa.id,
            sku=sku,
            nombre=nombre,
            tipo=tipo,
            categoria=categoria,
            unidad_codigo=unidad,
            costo_unitario=costo,
            atributos=atributos,
        )

        if tipo == "servicio":
            continue  # sin control de existencias

        almacen_principal = rng.choice(almacenes)
        entrada_inicial = rng.randint(30, 200)
        inventory_crud.registrar_movimiento(
            db,
            empresa_id=empresa.id,
            producto=producto,
            almacen=almacen_principal,
            tipo="entrada",
            cantidad=entrada_inicial,
            referencia="INV-INICIAL",
            nota="Carga inicial de inventario",
        )

        for _ in range(rng.randint(1, 4)):
            disponible = inventory_crud.disponible(
                db, producto_id=producto.id, almacen_id=almacen_principal.id
            )
            if disponible <= 1:
                break
            cantidad_salida = -rng.randint(1, min(15, disponible - 1))
            inventory_crud.registrar_movimiento(
                db,
                empresa_id=empresa.id,
                producto=producto,
                almacen=almacen_principal,
                tipo="salida",
                cantidad=cantidad_salida,
                referencia=f"VENTA-{rng.randint(1000, 9999)}",
            )

        if rng.random() < 0.25:
            inventory_crud.registrar_movimiento(
                db,
                empresa_id=empresa.id,
                producto=producto,
                almacen=almacen_principal,
                tipo="ajuste",
                cantidad=rng.choice([-2, -1, 1, 2, 3]),
                nota="Ajuste por conteo físico",
            )


def seed() -> None:
    db = SessionLocal()
    rng = random.Random(42)
    try:
        admin = get_or_create_usuario(db, email=ADMIN_EMAIL, password=DEMO_PASSWORD, nombre="Admin Demo")
        contador = get_or_create_usuario(
            db, email=CONTADOR_EMAIL, password=DEMO_PASSWORD, nombre="Contador Demo"
        )
        get_or_create_usuario(
            db,
            email=SUPERADMIN_EMAIL,
            password=DEMO_PASSWORD,
            nombre="Superadmin Nubinox",
            is_superadmin=True,
        )

        empresa = db.scalar(select(Empresa).where(Empresa.rfc == EMPRESA_RFC))
        if empresa is None:
            empresa = Empresa(
                rfc=EMPRESA_RFC, razon_social=EMPRESA_RAZON_SOCIAL, regimen_fiscal_codigo="601"
            )
            db.add(empresa)
            db.commit()
            db.refresh(empresa)

        ensure_membership(db, usuario=admin, empresa=empresa, rol_nombre="administrador")
        ensure_membership(db, usuario=contador, empresa=empresa, rol_nombre="contador")

        credenciales_crud.conectar(db, empresa_id=empresa.id, tipo="ciec")

        total_cfdis = db.scalar(
            select(Cfdi).where(Cfdi.empresa_id == empresa.id).limit(1)
        )
        if total_cfdis is None:
            nuevos = generar_cfdis_mock(
                db, empresa=empresa, cantidad=150, dias_atras=180, seed=42
            )
            alertas = rules_crud.evaluar_cfdis(db, nuevos)
            print(f"CFDIs generados: {len(nuevos)} (alertas: {alertas})")
        else:
            print("Ya existen CFDIs para la empresa demo, no se regeneran.")

        seed_inventario(db, empresa=empresa, rng=rng)

        print("Seed de demo OK:")
        print(f"  Empresa: {empresa.razon_social} ({empresa.rfc})")
        print(f"  Usuarios: {ADMIN_EMAIL} / {CONTADOR_EMAIL} / {SUPERADMIN_EMAIL} (password: {DEMO_PASSWORD})")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
