import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.modules.auth.models import Usuario
from app.modules.tenants.models import UsuarioEmpresa


def list_todos_usuarios(db: Session) -> list[tuple[Usuario, int]]:
    """Todos los usuarios del sistema con su número de empresas. Solo superadmin."""
    filas = db.execute(
        select(Usuario, func.count(UsuarioEmpresa.id))
        .outerjoin(UsuarioEmpresa, UsuarioEmpresa.usuario_id == Usuario.id)
        .group_by(Usuario.id)
        .order_by(Usuario.email)
    ).all()
    return [(usuario, num_empresas) for usuario, num_empresas in filas]


def crear_usuario(
    db: Session, *, email: str, password: str, nombre_completo: str | None, is_superadmin: bool
) -> Usuario:
    usuario = Usuario(
        email=email,
        hashed_password=hash_password(password),
        nombre_completo=nombre_completo,
        is_superadmin=is_superadmin,
    )
    db.add(usuario)
    db.commit()
    db.refresh(usuario)
    return usuario


def set_activo(db: Session, usuario: Usuario, activo: bool) -> Usuario:
    usuario.is_active = activo
    # Al desactivar, invalida también cualquier sesión ya emitida.
    if not activo:
        usuario.token_version += 1
    db.add(usuario)
    db.commit()
    db.refresh(usuario)
    return usuario


def eliminar_usuario(db: Session, usuario_id: uuid.UUID) -> None:
    usuario = db.get(Usuario, usuario_id)
    if usuario is not None:
        db.delete(usuario)
        db.commit()
