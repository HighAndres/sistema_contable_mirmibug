"""Clientes y proveedores. Permisos: terceros.leer · terceros.gestionar."""

import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.deps import EmpresaContext, require_permissions
from app.db.session import get_db
from app.modules.bitacora import crud as bitacora_crud
from app.modules.terceros import crud
from app.modules.terceros.schemas import (
    CargaTercerosResponse,
    SincronizarResponse,
    TerceroCreate,
    TerceroDetalleRead,
    TerceroResumenRead,
    TerceroUpdate,
)
from app.utils.tabular import ArchivoTabularError

router = APIRouter(prefix="/terceros", tags=["terceros"])


@router.get("", response_model=list[TerceroResumenRead])
def listar(
    tipo: str | None = Query(default=None, pattern="^(cliente|proveedor)$"),
    q: str | None = Query(default=None, max_length=120),
    activo: bool | None = None,
    ctx: EmpresaContext = Depends(require_permissions("terceros.leer")),
    db: Session = Depends(get_db),
) -> list[TerceroResumenRead]:
    return crud.a_resumen_lista(db, empresa_id=ctx.empresa.id, terceros=crud.listar(db, empresa_id=ctx.empresa.id, tipo=tipo, q=q, activo=activo))


@router.post("/sincronizar", response_model=SincronizarResponse)
def sincronizar(ctx: EmpresaContext = Depends(require_permissions("terceros.gestionar")), db: Session = Depends(get_db)) -> SincronizarResponse:
    """Detecta clientes y proveedores a partir de las contrapartes de los CFDI de la bóveda."""
    creados, actualizados = crud.sincronizar_desde_cfdi(db, empresa_id=ctx.empresa.id)
    total = len(crud.listar(db, empresa_id=ctx.empresa.id))
    bitacora_crud.registrar(db, empresa_id=ctx.empresa.id, usuario=ctx.usuario, accion="terceros.sincronizado", descripcion=f"Terceros detectados desde CFDI: {creados} nuevos, {actualizados} actualizados")
    return SincronizarResponse(creados=creados, actualizados=actualizados, total=total)


@router.get("/plantilla", response_class=Response)
def plantilla(ctx: EmpresaContext = Depends(require_permissions("terceros.leer"))) -> Response:
    return Response(content=crud.plantilla(), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": 'attachment; filename="plantilla_terceros.xlsx"'})


@router.post("/importar", response_model=CargaTercerosResponse)
async def importar(archivo: UploadFile = File(...), ctx: EmpresaContext = Depends(require_permissions("terceros.gestionar")), db: Session = Depends(get_db)) -> CargaTercerosResponse:
    try:
        c, a, e = crud.importar_excel(db, empresa_id=ctx.empresa.id, contenido=await archivo.read(), nombre=archivo.filename or "")
    except ArchivoTabularError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    bitacora_crud.registrar(db, empresa_id=ctx.empresa.id, usuario=ctx.usuario, accion="terceros.carga", descripcion=f"Carga masiva de terceros: {c} nuevos, {a} actualizados, {len(e)} con error", metadatos={"archivo": archivo.filename})
    return CargaTercerosResponse(creados=c, actualizados=a, errores=e)


@router.post("", response_model=TerceroDetalleRead, status_code=status.HTTP_201_CREATED)
def crear(payload: TerceroCreate, ctx: EmpresaContext = Depends(require_permissions("terceros.gestionar")), db: Session = Depends(get_db)) -> TerceroDetalleRead:
    if crud.get_por_rfc(db, empresa_id=ctx.empresa.id, rfc=payload.rfc):
        raise HTTPException(status.HTTP_409_CONFLICT, f"Ya existe un tercero con RFC {payload.rfc}")
    t = crud.crear(db, empresa_id=ctx.empresa.id, **payload.model_dump())
    bitacora_crud.registrar(db, empresa_id=ctx.empresa.id, usuario=ctx.usuario, accion="terceros.creado", descripcion=f"{t.tipo.capitalize()} {t.nombre} ({t.rfc}) registrado", entidad_tipo="tercero", entidad_id=t.id)
    return crud.a_detalle(db, empresa_id=ctx.empresa.id, tercero=t)


@router.get("/{tercero_id}", response_model=TerceroDetalleRead)
def detalle(tercero_id: uuid.UUID, ctx: EmpresaContext = Depends(require_permissions("terceros.leer")), db: Session = Depends(get_db)) -> TerceroDetalleRead:
    t = crud.get(db, empresa_id=ctx.empresa.id, tercero_id=tercero_id)
    if t is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tercero no encontrado")
    return crud.a_detalle(db, empresa_id=ctx.empresa.id, tercero=t)


@router.patch("/{tercero_id}", response_model=TerceroDetalleRead)
def actualizar(tercero_id: uuid.UUID, payload: TerceroUpdate, ctx: EmpresaContext = Depends(require_permissions("terceros.gestionar")), db: Session = Depends(get_db)) -> TerceroDetalleRead:
    t = crud.get(db, empresa_id=ctx.empresa.id, tercero_id=tercero_id)
    if t is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tercero no encontrado")
    cambios = payload.model_dump(exclude_unset=True)
    t = crud.actualizar(db, tercero=t, cambios=cambios)
    bitacora_crud.registrar(db, empresa_id=ctx.empresa.id, usuario=ctx.usuario, accion="terceros.actualizado", descripcion=f"{t.nombre} ({t.rfc}) actualizado: {', '.join(cambios)}", entidad_tipo="tercero", entidad_id=t.id)
    return crud.a_detalle(db, empresa_id=ctx.empresa.id, tercero=t)
