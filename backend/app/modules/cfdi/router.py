import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import EmpresaContext, require_permissions
from app.db.session import get_db
from app.modules.cfdi import crud
from app.modules.cfdi.schemas import CfdiDetalleRead, CfdiPage
from app.modules.rules import crud as rules_crud
from sqlalchemy.orm import Session

router = APIRouter(prefix="/cfdi", tags=["cfdi"])


@router.get("", response_model=CfdiPage)
def listar(
    tipo: str | None = None,
    direccion: str | None = None,
    estatus: str | None = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
    ctx: EmpresaContext = Depends(require_permissions("cfdi.leer")),
    db: Session = Depends(get_db),
) -> CfdiPage:
    items, total = crud.list_paginado(
        db,
        empresa_id=ctx.empresa.id,
        tipo=tipo,
        direccion=direccion,
        estatus=estatus,
        limit=limit,
        offset=offset,
    )
    return CfdiPage(items=items, total=total, limit=limit, offset=offset)


@router.get("/{cfdi_id}", response_model=CfdiDetalleRead)
def detalle(
    cfdi_id: uuid.UUID,
    ctx: EmpresaContext = Depends(require_permissions("cfdi.leer")),
    db: Session = Depends(get_db),
) -> CfdiDetalleRead:
    cfdi = crud.get(db, empresa_id=ctx.empresa.id, cfdi_id=cfdi_id)
    if cfdi is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "CFDI no encontrado")
    alertas = rules_crud.list_alertas_de_cfdi(db, cfdi_id=cfdi.id)
    return CfdiDetalleRead.model_validate(cfdi, from_attributes=True).model_copy(
        update={"alertas": alertas}
    )
