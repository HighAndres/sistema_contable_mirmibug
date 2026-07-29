from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import EmpresaContext, get_current_empresa, require_permissions
from app.db.session import get_db
from app.modules.bitacora import crud as bitacora_crud
from app.modules.credentials import crud
from app.modules.credentials.schemas import CredencialConectarRequest, CredencialRead

router = APIRouter(prefix="/credentials", tags=["credentials"])


@router.get("", response_model=CredencialRead | None)
def estado_credencial(
    ctx: EmpresaContext = Depends(get_current_empresa),
    db: Session = Depends(get_db),
) -> CredencialRead | None:
    return crud.get_por_empresa(db, ctx.empresa.id)


@router.post("/conectar", response_model=CredencialRead)
def conectar_sat(
    payload: CredencialConectarRequest,
    ctx: EmpresaContext = Depends(require_permissions("credenciales.gestionar")),
    db: Session = Depends(get_db),
) -> CredencialRead:
    credencial = crud.conectar(db, empresa_id=ctx.empresa.id, tipo=payload.tipo)
    bitacora_crud.registrar(
        db,
        empresa_id=ctx.empresa.id,
        usuario=ctx.usuario,
        accion="sat.conectado",
        descripcion=f"Conexión con el SAT establecida ({payload.tipo.upper()})",
    )
    return credencial
