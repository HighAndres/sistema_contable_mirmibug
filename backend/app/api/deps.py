"""Dependencias compartidas de la API: sesión, usuario actual y RBAC multi-empresa.

El permiso efectivo de un usuario depende de la empresa activa (header
X-Empresa-Id): el mismo usuario puede ser "administrador" en una empresa y
"contador" en otra, por eso require_permissions() resuelve el rol vía la
membresía usuario-empresa (tenants.models.UsuarioEmpresa), no vía el usuario.

Un usuario con is_superadmin=True es la excepción: opera sobre CUALQUIER
empresa del sistema (no necesita una fila en usuario_empresas) y siempre
tiene todos los permisos — es el rol de soporte/operación de la plataforma,
no un rol de negocio de una empresa en particular.
"""

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field

import jwt
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import ACCESS_TOKEN_TYPE, decode_token
from app.db.session import get_db
from app.modules.auth import crud as crud_user
from app.modules.auth.models import Permiso, Usuario

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_PREFIX}/auth/login")

_credentials_exc = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="No se pudieron validar las credenciales",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> Usuario:
    """Decodifica el access token y devuelve el usuario correspondiente.

    Valida el claim "tv" (token_version) contra el usuario actual: si la
    contraseña cambió después de emitido este token, tv ya no coincide y el
    token se rechaza de inmediato, aunque no haya expirado todavía.
    """
    try:
        payload = decode_token(token)
        if payload.get("type") != ACCESS_TOKEN_TYPE:
            raise _credentials_exc
        sub = payload.get("sub")
        if sub is None:
            raise _credentials_exc
        user_id = uuid.UUID(sub)
    except (jwt.PyJWTError, ValueError):
        raise _credentials_exc

    user = crud_user.get_by_id(db, user_id)
    if user is None or payload.get("tv") != user.token_version:
        raise _credentials_exc
    return user


def get_current_active_user(current_user: Usuario = Depends(get_current_user)) -> Usuario:
    if not current_user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Usuario inactivo")
    return current_user


def require_superadmin(current_user: Usuario = Depends(get_current_active_user)) -> Usuario:
    """Dependencia para endpoints de administración global de la plataforma
    (no ligados a una empresa): solo superadmin."""
    if not current_user.is_superadmin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Requiere privilegios de superadmin")
    return current_user


@dataclass
class EmpresaContext:
    """Empresa activa + permisos efectivos del usuario en ella, para el request actual."""

    usuario: Usuario
    empresa: "Empresa"  # noqa: F821 - forward ref, ver tenants.models
    rol_nombre: str
    permisos: set[str] = field(default_factory=set)


def get_current_empresa(
    x_empresa_id: uuid.UUID = Header(..., alias="X-Empresa-Id"),
    current_user: Usuario = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> EmpresaContext:
    from app.modules.tenants import crud as crud_tenants

    if current_user.is_superadmin:
        empresa = crud_tenants.get_empresa(db, empresa_id=x_empresa_id)
        if empresa is None or not empresa.activo:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Empresa no encontrada")
        todos_permisos = {p.codigo for p in db.scalars(select(Permiso)).all()}
        return EmpresaContext(usuario=current_user, empresa=empresa, rol_nombre="superadmin", permisos=todos_permisos)

    membresia = crud_tenants.get_membership(db, usuario_id=current_user.id, empresa_id=x_empresa_id)
    if membresia is None or not membresia.empresa.activo:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No tienes acceso a esta empresa")
    return EmpresaContext(
        usuario=current_user,
        empresa=membresia.empresa,
        rol_nombre=membresia.rol.nombre,
        permisos={p.codigo for p in membresia.rol.permisos},
    )


def require_permissions(*codes: str) -> Callable[..., EmpresaContext]:
    """Dependencia que exige que el usuario tenga TODOS los permisos dados en la empresa activa."""

    def checker(ctx: EmpresaContext = Depends(get_current_empresa)) -> EmpresaContext:
        faltantes = set(codes) - ctx.permisos
        if faltantes:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "No tienes permisos para realizar esta acción")
        return ctx

    return checker
