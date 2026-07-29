from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import EmpresaContext, get_current_active_user, require_permissions
from app.db.session import get_db
from app.modules.auth.models import Permiso, Usuario
from app.modules.bitacora import crud as bitacora_crud
from app.modules.tenants import crud
from app.modules.tenants.schemas import (
    EmpresaCreate,
    EmpresaRead,
    InvitarUsuarioRequest,
    InvitarUsuarioResponse,
    MiEmpresaRead,
    MiembroEmpresaRead,
)

router = APIRouter(prefix="/tenants", tags=["tenants"])


@router.get("/empresas/mias", response_model=list[MiEmpresaRead])
def mis_empresas(
    current_user: Usuario = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> list[MiEmpresaRead]:
    # Un superadmin no tiene membresías propias: opera sobre TODAS las
    # empresas del sistema, con todos los permisos en cada una.
    if current_user.is_superadmin:
        todos_permisos = [p.codigo for p in db.scalars(select(Permiso)).all()]
        return [
            MiEmpresaRead(empresa=empresa, rol="superadmin", permisos=todos_permisos)
            for empresa in crud.list_todas_empresas(db)
        ]

    membresias = crud.list_memberships_de_usuario(db, usuario_id=current_user.id)
    return [
        MiEmpresaRead(empresa=m.empresa, rol=m.rol.nombre, permisos=[p.codigo for p in m.rol.permisos])
        for m in membresias
    ]


@router.post("/empresas", response_model=EmpresaRead, status_code=status.HTTP_201_CREATED)
def crear_empresa(
    payload: EmpresaCreate,
    current_user: Usuario = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> EmpresaRead:
    try:
        empresa = crud.create_empresa_con_admin(
            db,
            usuario_id=current_user.id,
            rfc=payload.rfc,
            razon_social=payload.razon_social,
            regimen_fiscal_codigo=payload.regimen_fiscal_codigo,
        )
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya existe una empresa con este RFC")

    bitacora_crud.registrar(
        db,
        empresa_id=empresa.id,
        usuario=current_user,
        accion="empresa.creada",
        descripcion=f"Empresa {empresa.razon_social} ({empresa.rfc}) creada",
        entidad_tipo="empresa",
        entidad_id=empresa.id,
    )
    return empresa


@router.get("/usuarios", response_model=list[MiembroEmpresaRead])
def listar_usuarios(
    ctx: EmpresaContext = Depends(require_permissions("usuarios.leer")),
    db: Session = Depends(get_db),
) -> list[MiembroEmpresaRead]:
    miembros = crud.list_miembros(db, empresa_id=ctx.empresa.id)
    return [
        MiembroEmpresaRead(
            usuario_id=m.usuario.id,
            email=m.usuario.email,
            nombre_completo=m.usuario.nombre_completo,
            rol=m.rol.nombre,
            is_active=m.usuario.is_active,
        )
        for m in miembros
    ]


@router.post("/usuarios/invitar", response_model=InvitarUsuarioResponse, status_code=status.HTTP_201_CREATED)
def invitar_usuario(
    payload: InvitarUsuarioRequest,
    ctx: EmpresaContext = Depends(require_permissions("usuarios.invitar")),
    db: Session = Depends(get_db),
) -> InvitarUsuarioResponse:
    try:
        resultado = crud.invitar_usuario(
            db,
            empresa_id=ctx.empresa.id,
            email=payload.email,
            rol_nombre=payload.rol_nombre,
            nombre_completo=payload.nombre_completo,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))

    bitacora_crud.registrar(
        db,
        empresa_id=ctx.empresa.id,
        usuario=ctx.usuario,
        accion="usuarios.invitado",
        descripcion=f"Usuario {payload.email} agregado como {resultado.rol.nombre}",
        entidad_tipo="usuario",
        entidad_id=resultado.usuario.id,
    )
    return InvitarUsuarioResponse(
        email=resultado.usuario.email,
        rol=resultado.rol.nombre,
        usuario_nuevo=resultado.creado,
        password_temporal=resultado.password_temporal,
    )
