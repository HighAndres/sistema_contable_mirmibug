from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import EmpresaContext, require_permissions
from app.db.session import get_db
from app.modules.rules import crud

router = APIRouter(prefix="/rules", tags=["rules"])


@router.post("/evaluar")
def reevaluar(
    ctx: EmpresaContext = Depends(require_permissions("cfdi.leer")),
    db: Session = Depends(get_db),
) -> dict[str, int]:
    total = crud.evaluar_empresa(db, empresa_id=ctx.empresa.id)
    return {"alertas_generadas": total}
