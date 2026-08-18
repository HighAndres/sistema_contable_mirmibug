from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import EmpresaContext, require_permissions
from app.db.session import get_db
from app.modules.reports import crud
from app.modules.reports.schemas import DashboardKPIs, MesMonto, TopContraparte

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/dashboard", response_model=DashboardKPIs)
def dashboard(
    anio: int | None = Query(default=None, ge=2000, le=2100, description="Vacío = histórico completo"),
    mes: int | None = Query(default=None, ge=1, le=12, description="Vacío = anual"),
    ctx: EmpresaContext = Depends(require_permissions("reportes.leer")),
    db: Session = Depends(get_db),
) -> DashboardKPIs:
    return crud.dashboard_kpis(db, empresa=ctx.empresa, anio=anio, mes=mes)


@router.get("/mensual", response_model=list[MesMonto])
def mensual(
    meses: int = 6,
    anio: int | None = Query(default=None, ge=2000, le=2100),
    ctx: EmpresaContext = Depends(require_permissions("reportes.leer")),
    db: Session = Depends(get_db),
) -> list[MesMonto]:
    return crud.serie_mensual(db, empresa_id=ctx.empresa.id, meses=meses, anio=anio)


@router.get("/top-clientes", response_model=list[TopContraparte])
def top_clientes(
    limit: int = 5,
    anio: int | None = Query(default=None, ge=2000, le=2100),
    mes: int | None = Query(default=None, ge=1, le=12),
    ctx: EmpresaContext = Depends(require_permissions("reportes.leer")),
    db: Session = Depends(get_db),
) -> list[TopContraparte]:
    return crud.top_contrapartes(db, empresa_id=ctx.empresa.id, direccion="emitido", limit=limit, anio=anio, mes=mes)


@router.get("/top-proveedores", response_model=list[TopContraparte])
def top_proveedores(
    limit: int = 5,
    anio: int | None = Query(default=None, ge=2000, le=2100),
    mes: int | None = Query(default=None, ge=1, le=12),
    ctx: EmpresaContext = Depends(require_permissions("reportes.leer")),
    db: Session = Depends(get_db),
) -> list[TopContraparte]:
    return crud.top_contrapartes(db, empresa_id=ctx.empresa.id, direccion="recibido", limit=limit, anio=anio, mes=mes)
