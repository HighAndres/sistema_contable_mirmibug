import uuid

import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user
from app.core.config import settings
from app.core.security import (
    PASSWORD_RESET_TOKEN_TYPE,
    REFRESH_TOKEN_TYPE,
    create_access_token,
    create_password_reset_token,
    create_refresh_token,
    decode_token,
    verify_password,
    verify_password_o_dummy,
)
from app.db.session import get_db
from app.modules.auth import crud
from app.modules.auth.models import Usuario
from app.modules.auth.schemas import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    RefreshRequest,
    ResetPasswordRequest,
    Token,
    UsuarioCreate,
    UsuarioRead,
)

router = APIRouter(prefix="/auth", tags=["auth"])

_GENERIC_RESET_MSG = {"detail": "Si el correo existe, se enviaron instrucciones para restablecer la contraseña."}


def _issue_tokens(user: Usuario) -> Token:
    sub = str(user.id)
    return Token(
        access_token=create_access_token(sub, user.token_version),
        refresh_token=create_refresh_token(sub, user.token_version),
    )


def _log_dev_reset_link(user: Usuario, token: str) -> None:
    """Sin servicio de correo: el enlace se imprime a consola (solo para desarrollo)."""
    url = f"{settings.FRONTEND_URL}/reset-password?token={token}"
    print(f"[DEV] Reset de contraseña para {user.email}: {url}")


@router.post("/register", response_model=UsuarioRead, status_code=status.HTTP_201_CREATED)
def register(payload: UsuarioCreate, db: Session = Depends(get_db)) -> Usuario:
    if crud.get_by_email(db, payload.email) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya existe una cuenta con este correo")
    return crud.create_user(
        db, email=payload.email, password=payload.password, nombre_completo=payload.nombre_completo
    )


@router.post("/login", response_model=Token)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)) -> Token:
    user = crud.get_by_email(db, form.username)

    if user is not None and crud.esta_bloqueado(user):
        minutos = settings.LOGIN_BLOQUEO_MINUTOS
        raise HTTPException(
            status.HTTP_423_LOCKED,
            f"Cuenta bloqueada temporalmente por demasiados intentos fallidos. Intenta de nuevo en unos minutos "
            f"(bloqueo de hasta {minutos} min).",
        )

    # verify_password_o_dummy corre bcrypt aunque el usuario no exista, para
    # que la respuesta tarde lo mismo en ambos casos (evita filtrar por
    # temporización qué correos están registrados).
    credenciales_validas = verify_password_o_dummy(form.password, user.hashed_password if user else None)
    if not credenciales_validas:
        if user is not None:
            crud.registrar_intento_fallido(db, user)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Credenciales inválidas")

    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Usuario inactivo")

    crud.resetear_intentos(db, user)
    crud.touch_last_login(db, user)
    return _issue_tokens(user)


@router.post("/refresh", response_model=Token)
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)) -> Token:
    try:
        data = decode_token(payload.refresh_token)
        if data.get("type") != REFRESH_TOKEN_TYPE:
            raise jwt.InvalidTokenError("Tipo de token incorrecto")
        user_id = uuid.UUID(data["sub"])
    except (jwt.PyJWTError, ValueError, KeyError):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh token inválido")

    user = crud.get_by_id(db, user_id)
    if user is None or not user.is_active or data.get("tv") != user.token_version:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh token inválido")
    return _issue_tokens(user)


@router.get("/me", response_model=UsuarioRead)
def me(current_user: Usuario = Depends(get_current_active_user)) -> Usuario:
    return current_user


@router.post("/forgot-password")
def forgot_password(payload: ForgotPasswordRequest, db: Session = Depends(get_db)) -> dict[str, str]:
    """Respuesta genérica siempre (no revela si el correo existe)."""
    user = crud.get_by_email(db, payload.email)
    if user is not None and user.is_active:
        token = create_password_reset_token(str(user.id), user.hashed_password)
        _log_dev_reset_link(user, token)
    return _GENERIC_RESET_MSG


@router.post("/reset-password")
def reset_password(payload: ResetPasswordRequest, db: Session = Depends(get_db)) -> dict[str, str]:
    try:
        data = decode_token(payload.token)
        if data.get("type") != PASSWORD_RESET_TOKEN_TYPE:
            raise jwt.InvalidTokenError("Tipo de token incorrecto")
        user_id = uuid.UUID(data["sub"])
    except (jwt.PyJWTError, ValueError, KeyError):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "El enlace de restablecimiento es inválido o expiró")

    user = crud.get_by_id(db, user_id)
    # phash: invalida el token de un solo uso si la contraseña ya cambió desde que se emitió.
    if user is None or data.get("phash") != user.hashed_password[:16]:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "El enlace de restablecimiento es inválido o ya fue usado")

    crud.set_password(db, user, payload.new_password)
    crud.resetear_intentos(db, user)
    return {"detail": "Contraseña actualizada correctamente"}


@router.post("/change-password")
def change_password(
    payload: ChangePasswordRequest,
    current_user: Usuario = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    if not verify_password(payload.current_password, current_user.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "La contraseña actual no es correcta")
    crud.set_password(db, current_user, payload.new_password)
    return {"detail": "Contraseña actualizada correctamente"}
