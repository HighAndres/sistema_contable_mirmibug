import secrets
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.modules.auth.models import Rol, Usuario
from app.modules.tenants.models import Empresa, UsuarioEmpresa


def get_empresa(db: Session, *, empresa_id: uuid.UUID) -> Empresa | None:
    return db.get(Empresa, empresa_id)


def list_todas_empresas(db: Session) -> list[Empresa]:
    """Solo para superadmin: todas las empresas del sistema, sin filtrar por membresía."""
    return list(db.scalars(select(Empresa).order_by(Empresa.razon_social)))


def get_membership(db: Session, *, usuario_id: uuid.UUID, empresa_id: uuid.UUID) -> UsuarioEmpresa | None:
    return db.scalar(
        select(UsuarioEmpresa).where(
            UsuarioEmpresa.usuario_id == usuario_id,
            UsuarioEmpresa.empresa_id == empresa_id,
        )
    )


def list_memberships_de_usuario(db: Session, *, usuario_id: uuid.UUID) -> list[UsuarioEmpresa]:
    return list(
        db.scalars(select(UsuarioEmpresa).where(UsuarioEmpresa.usuario_id == usuario_id))
    )


def list_miembros(db: Session, *, empresa_id: uuid.UUID) -> list[UsuarioEmpresa]:
    return list(
        db.scalars(select(UsuarioEmpresa).where(UsuarioEmpresa.empresa_id == empresa_id))
    )


@dataclass
class ResultadoInvitacion:
    usuario: Usuario
    rol: Rol
    creado: bool
    password_temporal: str | None


def invitar_usuario(
    db: Session, *, empresa_id: uuid.UUID, email: str, rol_nombre: str, nombre_completo: str | None
) -> ResultadoInvitacion:
    """Crea una cuenta nueva con una contraseña temporal y la agrega a la empresa.

    Deliberadamente NO une a la empresa a un correo que ya tiene cuenta: un
    administrador de una empresa (incluso una que él mismo acaba de crear)
    no debe poder agregar a un usuario real ajeno a su empresa sin su
    consentimiento — eso sería crear una membresía no autorizada y, de paso,
    un oráculo para saber qué correos ya están registrados en la plataforma.
    Vincular una cuenta existente a otra empresa requiere un superadmin (ver
    modules/admin), que sí opera con esa autoridad a nivel de plataforma.

    Lanza ValueError si el rol no existe o si el correo ya tiene una cuenta.
    """
    rol = db.scalar(select(Rol).where(Rol.nombre == rol_nombre))
    if rol is None:
        raise ValueError(f"El rol '{rol_nombre}' no existe")

    if db.scalar(select(Usuario).where(Usuario.email == email)) is not None:
        raise ValueError(
            "Ya existe una cuenta con este correo. Por seguridad no se agrega automáticamente "
            "a otra empresa sin su consentimiento — pide a un superadmin que la vincule."
        )

    password_temporal = secrets.token_urlsafe(9)
    usuario = Usuario(email=email, hashed_password=hash_password(password_temporal), nombre_completo=nombre_completo)
    db.add(usuario)
    db.flush()

    db.add(UsuarioEmpresa(usuario_id=usuario.id, empresa_id=empresa_id, rol_id=rol.id))
    db.commit()
    db.refresh(usuario)
    return ResultadoInvitacion(usuario=usuario, rol=rol, creado=True, password_temporal=password_temporal)


def create_empresa_con_admin(
    db: Session, *, usuario_id: uuid.UUID, rfc: str, razon_social: str, regimen_fiscal_codigo: str | None
) -> Empresa:
    """Crea la empresa y hace al creador su 'administrador' en una sola transacción."""
    rol_admin = db.scalar(select(Rol).where(Rol.nombre == "administrador"))
    if rol_admin is None:
        raise RuntimeError("Rol 'administrador' no existe: corre scripts/seed_rbac.py primero")

    empresa = Empresa(
        rfc=rfc.upper(),
        razon_social=razon_social,
        regimen_fiscal_codigo=regimen_fiscal_codigo,
    )
    db.add(empresa)
    db.flush()

    membresia = UsuarioEmpresa(usuario_id=usuario_id, empresa_id=empresa.id, rol_id=rol_admin.id)
    db.add(membresia)
    db.commit()
    db.refresh(empresa)
    return empresa
