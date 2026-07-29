import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password, verify_password
from app.modules.auth.models import Usuario


def get_by_id(db: Session, user_id: uuid.UUID) -> Usuario | None:
    return db.get(Usuario, user_id)


def get_by_email(db: Session, email: str) -> Usuario | None:
    return db.scalar(select(Usuario).where(Usuario.email == email))


def create_user(
    db: Session, *, email: str, password: str, nombre_completo: str | None = None, is_superadmin: bool = False
) -> Usuario:
    user = Usuario(
        email=email,
        hashed_password=hash_password(password),
        nombre_completo=nombre_completo,
        is_superadmin=is_superadmin,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate(db: Session, *, email: str, password: str) -> Usuario | None:
    """Verifica credenciales. No aplica bloqueo — eso lo maneja el router (ver esta_bloqueado)."""
    user = get_by_email(db, email)
    if user is None or not verify_password(password, user.hashed_password):
        return None
    return user


def esta_bloqueado(user: Usuario) -> bool:
    return user.bloqueado_hasta is not None and user.bloqueado_hasta > datetime.now(timezone.utc)


def registrar_intento_fallido(db: Session, user: Usuario) -> None:
    user.intentos_fallidos += 1
    if user.intentos_fallidos >= settings.LOGIN_MAX_INTENTOS:
        user.bloqueado_hasta = datetime.now(timezone.utc) + timedelta(minutes=settings.LOGIN_BLOQUEO_MINUTOS)
        user.intentos_fallidos = 0
    db.add(user)
    db.commit()


def resetear_intentos(db: Session, user: Usuario) -> None:
    user.intentos_fallidos = 0
    user.bloqueado_hasta = None
    db.add(user)
    db.commit()


def touch_last_login(db: Session, user: Usuario) -> None:
    user.last_login_at = datetime.now(timezone.utc)
    db.add(user)
    db.commit()


def set_password(db: Session, user: Usuario, new_password: str) -> None:
    user.hashed_password = hash_password(new_password)
    # Invalida de inmediato cualquier access/refresh token emitido antes del
    # cambio (ver claim "tv" en core/security.py y su verificación en deps.py).
    user.token_version += 1
    db.add(user)
    db.commit()
