"""Administración global de la plataforma: solo accesible a superadmin.

A diferencia de tenants.router (usuarios de UNA empresa), aquí se gestionan
usuarios del sistema completo — por eso no depende de EmpresaContext/
X-Empresa-Id, solo de require_superadmin.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import require_superadmin
from app.db.session import get_db
from app.modules.admin import crud
from app.modules.admin.schemas import UsuarioAdminCreate, UsuarioAdminRead
from app.modules.auth.models import Usuario

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/usuarios", response_model=list[UsuarioAdminRead])
def listar_usuarios(
    _superadmin: Usuario = Depends(require_superadmin),
    db: Session = Depends(get_db),
) -> list[UsuarioAdminRead]:
    return [
        UsuarioAdminRead(
            id=u.id,
            email=u.email,
            nombre_completo=u.nombre_completo,
            is_active=u.is_active,
            is_superadmin=u.is_superadmin,
            num_empresas=n,
            created_at=u.created_at,
        )
        for u, n in crud.list_todos_usuarios(db)
    ]


@router.post("/usuarios", response_model=UsuarioAdminRead, status_code=status.HTTP_201_CREATED)
def crear_usuario(
    payload: UsuarioAdminCreate,
    _superadmin: Usuario = Depends(require_superadmin),
    db: Session = Depends(get_db),
) -> UsuarioAdminRead:
    try:
        usuario = crud.crear_usuario(
            db,
            email=payload.email,
            password=payload.password,
            nombre_completo=payload.nombre_completo,
            is_superadmin=payload.is_superadmin,
        )
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya existe una cuenta con este correo")
    return UsuarioAdminRead(
        id=usuario.id,
        email=usuario.email,
        nombre_completo=usuario.nombre_completo,
        is_active=usuario.is_active,
        is_superadmin=usuario.is_superadmin,
        num_empresas=0,
        created_at=usuario.created_at,
    )


def _resolver_usuario_o_404(db: Session, usuario_id: uuid.UUID) -> Usuario:
    usuario = db.get(Usuario, usuario_id)
    if usuario is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuario no encontrado")
    return usuario


@router.post("/usuarios/{usuario_id}/desactivar", response_model=UsuarioAdminRead)
def desactivar_usuario(
    usuario_id: uuid.UUID,
    superadmin: Usuario = Depends(require_superadmin),
    db: Session = Depends(get_db),
) -> UsuarioAdminRead:
    if usuario_id == superadmin.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No puedes desactivar tu propia cuenta")
    usuario = crud.set_activo(db, _resolver_usuario_o_404(db, usuario_id), activo=False)
    return UsuarioAdminRead(
        id=usuario.id,
        email=usuario.email,
        nombre_completo=usuario.nombre_completo,
        is_active=usuario.is_active,
        is_superadmin=usuario.is_superadmin,
        num_empresas=0,
        created_at=usuario.created_at,
    )


@router.post("/usuarios/{usuario_id}/activar", response_model=UsuarioAdminRead)
def activar_usuario(
    usuario_id: uuid.UUID,
    _superadmin: Usuario = Depends(require_superadmin),
    db: Session = Depends(get_db),
) -> UsuarioAdminRead:
    usuario = crud.set_activo(db, _resolver_usuario_o_404(db, usuario_id), activo=True)
    return UsuarioAdminRead(
        id=usuario.id,
        email=usuario.email,
        nombre_completo=usuario.nombre_completo,
        is_active=usuario.is_active,
        is_superadmin=usuario.is_superadmin,
        num_empresas=0,
        created_at=usuario.created_at,
    )


@router.delete("/usuarios/{usuario_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_usuario(
    usuario_id: uuid.UUID,
    superadmin: Usuario = Depends(require_superadmin),
    db: Session = Depends(get_db),
) -> None:
    if usuario_id == superadmin.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No puedes eliminar tu propia cuenta")
    _resolver_usuario_o_404(db, usuario_id)
    crud.eliminar_usuario(db, usuario_id)
