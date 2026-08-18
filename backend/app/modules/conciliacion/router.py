"""Conciliación bancaria y fiscal.

Permisos: conciliacion.leer (ver) · conciliacion.gestionar (cuentas, importar,
conciliar, capturar declaraciones).
"""

import uuid
from datetime import date

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import EmpresaContext, require_permissions
from app.db.session import get_db
from app.modules.bitacora import crud as bitacora_crud
from app.modules.cfdi import crud as cfdi_crud
from app.modules.conciliacion import crud
from app.modules.conciliacion.importador import ImportacionError, importar_estado_cuenta
from app.modules.conciliacion.schemas import (
    AutoConciliarRequest,
    AutoConciliarResponse,
    CandidatoCfdi,
    ConciliarRequest,
    CuentaCreate,
    CuentaRead,
    DeclaracionRead,
    DeclaracionUpsert,
    IgnorarRequest,
    ImportarBancoResponse,
    MovimientoBancoRead,
    MovimientosPageRead,
    ResumenConciliacion,
)

router = APIRouter(prefix="/conciliacion", tags=["conciliacion"])
MAX_ARCHIVO = 10 * 1024 * 1024




# ---------- Cuentas ----------


@router.get("/cuentas", response_model=list[CuentaRead])
def cuentas(ctx: EmpresaContext = Depends(require_permissions("conciliacion.leer")), db: Session = Depends(get_db)):
    return crud.listar_cuentas(db, empresa_id=ctx.empresa.id)


@router.post("/cuentas", response_model=CuentaRead, status_code=status.HTTP_201_CREATED)
def crear_cuenta(payload: CuentaCreate, ctx: EmpresaContext = Depends(require_permissions("conciliacion.gestionar")), db: Session = Depends(get_db)):
    if any(c.alias.lower() == payload.alias.lower() for c in crud.listar_cuentas(db, empresa_id=ctx.empresa.id)):
        raise HTTPException(status.HTTP_409_CONFLICT, f"Ya existe una cuenta con el alias '{payload.alias}'")
    cuenta = crud.crear_cuenta(db, empresa_id=ctx.empresa.id, **payload.model_dump())
    bitacora_crud.registrar(db, empresa_id=ctx.empresa.id, usuario=ctx.usuario, accion="banco.cuenta_creada", descripcion=f"Cuenta bancaria '{cuenta.alias}' ({cuenta.banco}) registrada", entidad_tipo="cuenta_bancaria", entidad_id=cuenta.id)
    return cuenta


# ---------- Movimientos ----------


@router.post("/bancos/importar", response_model=ImportarBancoResponse, status_code=status.HTTP_201_CREATED)
async def importar_banco(
    archivo: UploadFile = File(...),
    cuenta_id: uuid.UUID = Form(...),
    ctx: EmpresaContext = Depends(require_permissions("conciliacion.gestionar")),
    db: Session = Depends(get_db),
) -> ImportarBancoResponse:
    """Sube el estado de cuenta (Excel o CSV) y registra los movimientos; las
    filas ya importadas antes se detectan y no se duplican."""
    cuenta = crud.get_cuenta(db, empresa_id=ctx.empresa.id, cuenta_id=cuenta_id)
    if cuenta is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cuenta bancaria no encontrada")
    contenido = await archivo.read()
    if len(contenido) > MAX_ARCHIVO:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "El archivo supera 10 MB")
    try:
        filas, mapa, adv = importar_estado_cuenta(contenido, archivo.filename or "")
    except ImportacionError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    nuevos, dup = crud.importar_filas(db, empresa_id=ctx.empresa.id, cuenta=cuenta, filas=filas, archivo_nombre=(archivo.filename or "")[:120] or None)
    if dup:
        adv.append(f"{dup} movimientos ya estaban importados y se omitieron.")
    bitacora_crud.registrar(
        db, empresa_id=ctx.empresa.id, usuario=ctx.usuario, accion="banco.importado",
        descripcion=f"Estado de cuenta importado a '{cuenta.alias}': {nuevos} movimientos nuevos, {dup} duplicados",
        entidad_tipo="cuenta_bancaria", entidad_id=cuenta.id, metadatos={"archivo": archivo.filename, "nuevos": nuevos, "duplicados": dup},
    )
    fechas = [f.fecha for f in filas]
    return ImportarBancoResponse(cuenta_id=cuenta.id, importados=nuevos, duplicados=dup, columnas_detectadas=mapa, advertencias=adv, fecha_min=min(fechas), fecha_max=max(fechas))


@router.get("/bancos/movimientos", response_model=MovimientosPageRead)
def movimientos(
    cuenta_id: uuid.UUID | None = None,
    anio: int | None = Query(default=None, ge=2000, le=2100),
    mes: int | None = Query(default=None, ge=1, le=12),
    estado: str | None = Query(default=None, pattern="^(pendiente|conciliado|ignorado)$"),
    q: str | None = Query(default=None, max_length=120),
    limit: int = Query(default=200, le=1000),
    offset: int = 0,
    ctx: EmpresaContext = Depends(require_permissions("conciliacion.leer")),
    db: Session = Depends(get_db),
) -> MovimientosPageRead:
    items, total = crud.listar_movimientos(db, empresa_id=ctx.empresa.id, cuenta_id=cuenta_id, anio=anio, mes=mes, estado=estado, q=q, limit=limit, offset=offset)
    return MovimientosPageRead(items=[crud.a_movimiento_read(m) for m in items], total=total)


def _mov_or_404(db, ctx, movimiento_id):
    m = crud.get_movimiento(db, empresa_id=ctx.empresa.id, movimiento_id=movimiento_id)
    if m is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Movimiento no encontrado")
    return m


@router.get("/bancos/movimientos/{movimiento_id}/candidatos", response_model=list[CandidatoCfdi])
def candidatos(
    movimiento_id: uuid.UUID,
    tolerancia_dias: int = Query(default=5, ge=0, le=60),
    ctx: EmpresaContext = Depends(require_permissions("conciliacion.leer")),
    db: Session = Depends(get_db),
):
    return crud.candidatos_para(db, mov=_mov_or_404(db, ctx, movimiento_id), tolerancia_dias=tolerancia_dias)


@router.post("/bancos/movimientos/{movimiento_id}/conciliar", response_model=MovimientoBancoRead)
def conciliar_manual(movimiento_id: uuid.UUID, payload: ConciliarRequest, ctx: EmpresaContext = Depends(require_permissions("conciliacion.gestionar")), db: Session = Depends(get_db)):
    mov = _mov_or_404(db, ctx, movimiento_id)
    cfdi = cfdi_crud.get(db, empresa_id=ctx.empresa.id, cfdi_id=payload.cfdi_id)
    if cfdi is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "CFDI no encontrado")
    return crud.a_movimiento_read(crud.conciliar(db, mov=mov, cfdi=cfdi, por="manual", nota=payload.nota))


@router.post("/bancos/movimientos/{movimiento_id}/desconciliar", response_model=MovimientoBancoRead)
def desconciliar(movimiento_id: uuid.UUID, ctx: EmpresaContext = Depends(require_permissions("conciliacion.gestionar")), db: Session = Depends(get_db)):
    return crud.a_movimiento_read(crud.desconciliar(db, mov=_mov_or_404(db, ctx, movimiento_id)))


@router.post("/bancos/movimientos/{movimiento_id}/ignorar", response_model=MovimientoBancoRead)
def ignorar(movimiento_id: uuid.UUID, payload: IgnorarRequest, ctx: EmpresaContext = Depends(require_permissions("conciliacion.gestionar")), db: Session = Depends(get_db)):
    """Marca el movimiento como no conciliable con CFDI (comisiones, traspasos, intereses...)."""
    return crud.a_movimiento_read(crud.ignorar(db, mov=_mov_or_404(db, ctx, movimiento_id), nota=payload.nota))


@router.post("/bancos/auto", response_model=AutoConciliarResponse)
def auto(payload: AutoConciliarRequest, ctx: EmpresaContext = Depends(require_permissions("conciliacion.gestionar")), db: Session = Depends(get_db)):
    rev, conc, sin, amb = crud.auto_conciliar(db, empresa_id=ctx.empresa.id, cuenta_id=payload.cuenta_id, anio=payload.anio, mes=payload.mes, tolerancia_dias=payload.tolerancia_dias)
    bitacora_crud.registrar(db, empresa_id=ctx.empresa.id, usuario=ctx.usuario, accion="banco.auto_conciliado", descripcion=f"Conciliación automática: {conc} de {rev} movimientos ligados a CFDI ({amb} ambiguos, {sin} sin coincidencia)")
    return AutoConciliarResponse(revisados=rev, conciliados=conc, sin_coincidencia=sin, ambiguos=amb)


# ---------- Declaraciones y resumen ----------


@router.get("/declaraciones/{anio}/{mes}", response_model=DeclaracionRead)
def declaracion(anio: int, mes: int, ctx: EmpresaContext = Depends(require_permissions("conciliacion.leer")), db: Session = Depends(get_db)):
    return crud.a_declaracion_read(crud.get_declaracion(db, empresa_id=ctx.empresa.id, anio=anio, mes=mes), anio=anio, mes=mes)


@router.put("/declaraciones/{anio}/{mes}", response_model=DeclaracionRead)
def guardar_declaracion(anio: int, mes: int, payload: DeclaracionUpsert, ctx: EmpresaContext = Depends(require_permissions("conciliacion.gestionar")), db: Session = Depends(get_db)):
    if not (2000 <= anio <= 2100 and 1 <= mes <= 12):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Periodo inválido")
    d = crud.upsert_declaracion(db, empresa_id=ctx.empresa.id, anio=anio, mes=mes, datos=payload.model_dump(exclude_unset=True))
    bitacora_crud.registrar(db, empresa_id=ctx.empresa.id, usuario=ctx.usuario, accion="declaracion.capturada", descripcion=f"Declaración {mes:02d}/{anio} capturada (IVA {d.iva_declarado}, ISR {d.isr_declarado})", entidad_tipo="declaracion", entidad_id=d.id)
    return crud.a_declaracion_read(d, anio=anio, mes=mes)


@router.get("/resumen", response_model=ResumenConciliacion)
def resumen(
    anio: int = Query(default=None, ge=2000, le=2100),
    mes: int = Query(default=None, ge=1, le=12),
    ctx: EmpresaContext = Depends(require_permissions("conciliacion.leer")),
    db: Session = Depends(get_db),
) -> ResumenConciliacion:
    """SAT (bóveda) vs banco vs declarado para el mes."""
    hoy = date.today()
    return crud.resumen(db, empresa=ctx.empresa, anio=anio or hoy.year, mes=mes or hoy.month)
