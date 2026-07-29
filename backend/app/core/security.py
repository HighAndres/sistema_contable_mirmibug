"""Utilidades de seguridad: hashing de contraseñas y tokens JWT."""

from datetime import datetime, timedelta, timezone

import jwt
from passlib.context import CryptContext

from app.core.config import settings

# bcrypt fijado en 4.0.1 (ver requirements.txt) por compatibilidad con passlib.
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Hash "señuelo" contra el que se compara cuando el usuario no existe, para
# que /auth/login tarde lo mismo exista o no la cuenta (si no se hiciera esto,
# la ausencia de un hash con qué comparar hace la respuesta perceptiblemente
# más rápida, filtrando por temporización qué correos están registrados).
_DUMMY_HASH = pwd_context.hash("nubinox-dummy-password-para-tiempo-constante")

# Tipos de token (claim "type").
ACCESS_TOKEN_TYPE = "access"
REFRESH_TOKEN_TYPE = "refresh"
PASSWORD_RESET_TOKEN_TYPE = "password_reset"


def hash_password(password: str) -> str:
    """Devuelve el hash bcrypt de una contraseña en claro."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifica una contraseña en claro contra su hash almacenado."""
    return pwd_context.verify(plain_password, hashed_password)


def verify_password_o_dummy(plain_password: str, hashed_password: str | None) -> bool:
    """Como verify_password, pero si no hay hash (usuario inexistente) igual
    corre bcrypt contra un hash señuelo, para no filtrar por tiempo de
    respuesta si el correo existe o no."""
    return pwd_context.verify(plain_password, hashed_password or _DUMMY_HASH) and hashed_password is not None


def _create_token(subject: str, token_type: str, expires_delta: timedelta, token_version: int) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,  # id del usuario (UUID en str)
        "type": token_type,
        "tv": token_version,
        "iat": now,
        "exp": now + expires_delta,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_access_token(subject: str, token_version: int) -> str:
    return _create_token(
        subject, ACCESS_TOKEN_TYPE, timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES), token_version
    )


def create_refresh_token(subject: str, token_version: int) -> str:
    return _create_token(
        subject, REFRESH_TOKEN_TYPE, timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS), token_version
    )


def create_password_reset_token(subject: str, pwd_hash: str) -> str:
    """Token de un solo uso: embebe un prefijo del hash actual (claim "phash").

    Si la contraseña cambia (por este u otro medio), el prefijo ya no coincide
    y el token queda invalidado sin necesitar una tabla de tokens usados.
    """
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "type": PASSWORD_RESET_TOKEN_TYPE,
        "iat": now,
        "exp": now + timedelta(minutes=settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES),
        "phash": pwd_hash[:16],
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    """Decodifica y valida firma/expiración. Lanza jwt.PyJWTError si es inválido."""
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
