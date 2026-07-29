"""Fixtures compartidos de pytest.

Usa una base de datos Postgres separada ("nubinox_test" por defecto, o
POSTGRES_DB si ya se sobreescribió antes de importar este módulo) y aísla
cada test en su propia transacción externa con un SAVEPOINT interno
(join_transaction_mode="create_savepoint"): aunque el código bajo prueba
llame a db.commit() (como hace toda la capa crud/), el rollback de la
transacción externa al final del test deshace TODO, dejando la base limpia
para el siguiente test sin tener que recrear el esquema cada vez.
"""

import os

# Deben fijarse ANTES de importar cualquier módulo de app.*, porque
# app.core.config.settings se instancia una sola vez al importarse.
os.environ.setdefault("POSTGRES_DB", "nubinox_test")
os.environ.setdefault("SECRET_KEY", "test-secret-key-no-usar-en-produccion")
os.environ.setdefault("DEBUG", "true")
os.environ.setdefault("BACKEND_CORS_ORIGINS", "")

import uuid  # noqa: E402

import psycopg2  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session as SASession  # noqa: E402

import app.modules.admin  # noqa: E402,F401
import app.modules.auth.models  # noqa: E402,F401
import app.modules.bitacora.models  # noqa: E402,F401
import app.modules.catalogs.models  # noqa: E402,F401
import app.modules.cfdi.models  # noqa: E402,F401
import app.modules.credentials.models  # noqa: E402,F401
import app.modules.inventory.models  # noqa: E402,F401
import app.modules.rules.models  # noqa: E402,F401
import app.modules.tenants.models  # noqa: E402,F401
from app.core.config import settings  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.modules.auth.models import Permiso, Rol, Usuario  # noqa: E402
from app.modules.tenants.models import Empresa, UsuarioEmpresa  # noqa: E402


def _ensure_test_database() -> None:
    conn = psycopg2.connect(
        dbname="postgres",
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT,
    )
    conn.autocommit = True
    try:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (settings.POSTGRES_DB,))
        if not cur.fetchone():
            cur.execute(f'CREATE DATABASE "{settings.POSTGRES_DB}"')
    finally:
        conn.close()


@pytest.fixture(scope="session")
def engine():
    _ensure_test_database()
    eng = create_engine(settings.DATABASE_URL)
    Base.metadata.drop_all(eng)
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture()
def db(engine):
    """Sesión aislada por test: se envuelve en una transacción externa que
    siempre se revierte, sin importar cuántos commit() haga el código bajo
    prueba (ver join_transaction_mode)."""
    connection = engine.connect()
    outer_transaction = connection.begin()
    session = SASession(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        outer_transaction.rollback()
        connection.close()


@pytest.fixture()
def client(db):
    def _override_get_db():
        yield db

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# --- Semillas mínimas reutilizables (espejo simplificado de scripts/seed_rbac.py) ---

PERMISOS_TEST = [
    "empresas.leer",
    "usuarios.leer",
    "usuarios.invitar",
    "credenciales.gestionar",
    "sat.sincronizar",
    "cfdi.leer",
    "reportes.leer",
    "inventario.leer",
    "inventario.ajustar",
    "bitacora.leer",
]


@pytest.fixture()
def seed_rbac(db):
    permisos = {codigo: Permiso(codigo=codigo) for codigo in PERMISOS_TEST}
    db.add_all(permisos.values())
    db.flush()

    admin_rol = Rol(nombre="administrador", es_sistema=True, permisos=list(permisos.values()))
    contador_rol = Rol(
        nombre="contador",
        es_sistema=True,
        permisos=[
            permisos["empresas.leer"],
            permisos["sat.sincronizar"],
            permisos["cfdi.leer"],
            permisos["reportes.leer"],
            permisos["inventario.leer"],
            permisos["inventario.ajustar"],
        ],
    )
    db.add_all([admin_rol, contador_rol])
    db.commit()
    return {"permisos": permisos, "administrador": admin_rol, "contador": contador_rol}


def crear_usuario(db, *, email: str = None, password: str = "Demo1234!", is_superadmin: bool = False) -> Usuario:
    email = email or f"{uuid.uuid4().hex[:12]}@test.nubinox"
    usuario = Usuario(email=email, hashed_password=hash_password(password), is_superadmin=is_superadmin)
    db.add(usuario)
    db.commit()
    db.refresh(usuario)
    return usuario


def crear_empresa(db, *, rfc: str = None, razon_social: str = "Empresa de Prueba SA de CV") -> Empresa:
    rfc = rfc or f"TST{uuid.uuid4().hex[:9].upper()}"
    empresa = Empresa(rfc=rfc, razon_social=razon_social)
    db.add(empresa)
    db.commit()
    db.refresh(empresa)
    return empresa


def agregar_membresia(db, *, usuario: Usuario, empresa: Empresa, rol: Rol) -> UsuarioEmpresa:
    membresia = UsuarioEmpresa(usuario_id=usuario.id, empresa_id=empresa.id, rol_id=rol.id)
    db.add(membresia)
    db.commit()
    return membresia


@pytest.fixture()
def empresa_admin(db, seed_rbac):
    """Un usuario administrador con su empresa ya montada; devuelve (usuario, empresa, password)."""
    password = "Demo1234!"
    usuario = crear_usuario(db, password=password)
    empresa = crear_empresa(db)
    agregar_membresia(db, usuario=usuario, empresa=empresa, rol=seed_rbac["administrador"])
    return usuario, empresa, password


def auth_headers(client: TestClient, *, email: str, password: str, empresa_id=None) -> dict:
    res = client.post("/api/v1/auth/login", data={"username": email, "password": password})
    assert res.status_code == 200, res.text
    token = res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    if empresa_id is not None:
        headers["X-Empresa-Id"] = str(empresa_id)
    return headers
