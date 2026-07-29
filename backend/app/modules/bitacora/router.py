from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import EmpresaContext, require_permissions
from app.db.session import get_db
from app.modules.bitacora import crud
from app.modules.bitacora.schemas import BitacoraRead

router = APIRouter(prefix="/bitacora", tags=["bitacora"])


@router.get("", response_model=list[BitacoraRead])
def listar(
    accion: str | None = None,
    limit: int = 100,
    offset: int = 0,
    ctx: EmpresaContext = Depends(require_permissions("bitacora.leer")),
    db: Session = Depends(get_db),
) -> list[BitacoraRead]:
    return crud.listar(db, empresa_id=ctx.empresa.id, accion=accion, limit=limit, offset=offset)
