from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user
from app.db.session import get_db
from app.modules.catalogs import crud
from app.modules.catalogs.schemas import CatalogoRead
from app.modules.auth.models import Usuario

router = APIRouter(prefix="/catalogs", tags=["catalogs"])


@router.get("/{tipo}", response_model=list[CatalogoRead])
def listar_catalogo(
    tipo: str,
    db: Session = Depends(get_db),
    _current_user: Usuario = Depends(get_current_active_user),
) -> list[CatalogoRead]:
    return crud.list_por_tipo(db, tipo)
