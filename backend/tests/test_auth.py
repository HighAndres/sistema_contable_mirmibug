"""Pruebas del módulo auth: login, bloqueo por intentos fallidos, reset/cambio
de contraseña e invalidación de tokens (los 4 hallazgos de la revisión de
seguridad)."""

from app.core.config import settings
from app.core.security import decode_token
from tests.conftest import crear_usuario


def test_register_and_login(client):
    res = client.post(
        "/api/v1/auth/register",
        json={"email": "nueva@test.nubinox", "password": "ClaveValida123!", "nombre_completo": "Nueva Persona"},
    )
    assert res.status_code == 201, res.text

    res = client.post("/api/v1/auth/login", data={"username": "nueva@test.nubinox", "password": "ClaveValida123!"})
    assert res.status_code == 200
    body = res.json()
    assert "access_token" in body and "refresh_token" in body


def test_login_wrong_password_fails(client, db):
    crear_usuario(db, email="usuario@test.nubinox", password="ClaveValida123!")
    res = client.post("/api/v1/auth/login", data={"username": "usuario@test.nubinox", "password": "incorrecta"})
    assert res.status_code == 401


def test_password_min_length_enforced(client):
    res = client.post(
        "/api/v1/auth/register", json={"email": "corta@test.nubinox", "password": "corta"}
    )
    assert res.status_code == 422


def test_login_lockout_after_max_attempts(client, db):
    crear_usuario(db, email="bloqueable@test.nubinox", password="ClaveValida123!")

    for _ in range(settings.LOGIN_MAX_INTENTOS):
        res = client.post(
            "/api/v1/auth/login", data={"username": "bloqueable@test.nubinox", "password": "mala"}
        )
        assert res.status_code == 401

    # El siguiente intento, aunque la contraseña sea correcta, debe estar bloqueado.
    res = client.post(
        "/api/v1/auth/login", data={"username": "bloqueable@test.nubinox", "password": "ClaveValida123!"}
    )
    assert res.status_code == 423


def test_forgot_password_always_returns_generic_message(client, db):
    crear_usuario(db, email="existe@test.nubinox", password="ClaveValida123!")

    res_existe = client.post("/api/v1/auth/forgot-password", json={"email": "existe@test.nubinox"})
    res_no_existe = client.post("/api/v1/auth/forgot-password", json={"email": "no.existe@test.nubinox"})

    assert res_existe.status_code == 200
    assert res_no_existe.status_code == 200
    assert res_existe.json() == res_no_existe.json()


def test_change_password_wrong_current_rejected(client, db):
    crear_usuario(db, email="cambia@test.nubinox", password="ClaveValida123!")
    login = client.post("/api/v1/auth/login", data={"username": "cambia@test.nubinox", "password": "ClaveValida123!"})
    token = login.json()["access_token"]

    res = client.post(
        "/api/v1/auth/change-password",
        headers={"Authorization": f"Bearer {token}"},
        json={"current_password": "incorrecta", "new_password": "OtraClaveValida123!"},
    )
    assert res.status_code == 401


def test_change_password_invalidates_previous_tokens(client, db):
    crear_usuario(db, email="rota@test.nubinox", password="ClaveValida123!")
    login = client.post("/api/v1/auth/login", data={"username": "rota@test.nubinox", "password": "ClaveValida123!"})
    old_access = login.json()["access_token"]
    old_refresh = login.json()["refresh_token"]

    # El token viejo funciona antes del cambio.
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {old_access}"}).status_code == 200

    change = client.post(
        "/api/v1/auth/change-password",
        headers={"Authorization": f"Bearer {old_access}"},
        json={"current_password": "ClaveValida123!", "new_password": "OtraClaveValida123!"},
    )
    assert change.status_code == 200

    # El mismo access token ya no debe servir.
    res_me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {old_access}"})
    assert res_me.status_code == 401

    # El refresh token viejo tampoco.
    res_refresh = client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
    assert res_refresh.status_code == 401

    # Pero se puede volver a iniciar sesión con la contraseña nueva.
    relogin = client.post(
        "/api/v1/auth/login", data={"username": "rota@test.nubinox", "password": "OtraClaveValida123!"}
    )
    assert relogin.status_code == 200


def test_reset_password_token_is_single_use(client, db):
    from app.core.security import create_password_reset_token

    usuario = crear_usuario(db, email="reset@test.nubinox", password="ClaveValida123!")
    token = create_password_reset_token(str(usuario.id), usuario.hashed_password)

    res1 = client.post(
        "/api/v1/auth/reset-password", json={"token": token, "new_password": "NuevaClave123!"}
    )
    assert res1.status_code == 200

    # El mismo token ya no sirve: el phash embebido ya no coincide (la
    # contraseña cambió), aunque el JWT en sí no haya expirado.
    res2 = client.post(
        "/api/v1/auth/reset-password", json={"token": token, "new_password": "OtraClave456!"}
    )
    assert res2.status_code == 400


def test_access_token_carries_token_version_claim(client, db):
    usuario = crear_usuario(db, email="claim@test.nubinox", password="ClaveValida123!")
    login = client.post("/api/v1/auth/login", data={"username": "claim@test.nubinox", "password": "ClaveValida123!"})
    payload = decode_token(login.json()["access_token"])
    assert payload["tv"] == usuario.token_version
