"""Endpoints de pedimentos de importación y costeo.

Permisos:
    pedimentos.leer       ver pedimentos y su costeo
    pedimentos.gestionar  importar M3 / capturar / configurar prorrateo / aplicar al inventario
"""

import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import EmpresaContext, require_permissions
from app.db.session import get_db
from app.modules.bitacora import crud as bitacora_crud
from app.modules.inventory import crud as inventory_crud
from app.modules.pedimentos import conceptos as conceptos_mod
from app.modules.pedimentos import crud
from app.modules.pedimentos.crud import AplicarInventarioError, PedimentoAplicadoError, PedimentoDuplicadoError
from app.modules.pedimentos.parser_m3 import M3ParseError, parse_m3
from app.modules.pedimentos.schemas import (
    AplicarInventarioRequest,
    AplicarInventarioResponse,
    ImportarM3Response,
    PartidaRead,
    PartidaUpdate,
    PedimentoCreate,
    PedimentoDetalleRead,
    PedimentoResumenRead,
    PedimentoUpdate,
)
from app.modules.pedimentos.umc import UMC
from app.utils.tabular import ArchivoTabularError

router = APIRouter(prefix="/pedimentos", tags=["pedimentos"])

MAX_M3_BYTES = 2 * 1024 * 1024  # un M3 real pesa ~10 KB; 2 MB es holgadísimo


def _get_or_404(db: Session, ctx: EmpresaContext, pedimento_id: uuid.UUID):
    ped = crud.get(db, empresa_id=ctx.empresa.id, pedimento_id=pedimento_id)
    if ped is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pedimento no encontrado")
    return ped


@router.get("/umc", response_model=dict[str, dict[str, str]])
def catalogo_umc(ctx: EmpresaContext = Depends(require_permissions("pedimentos.leer"))) -> dict:
    """Unidades de medida del pedimento y su clave SAT para facturar."""
    return {k: {"descripcion": d, "clave_sat": s} for k, (d, s) in UMC.items()}


class ConceptoSatRead(BaseModel):
    id: uuid.UUID
    concepto: str
    clave_prodserv: str
    clave_unidad_sat: str | None


class ConceptosPage(BaseModel):
    items: list[ConceptoSatRead]
    total: int


class ConceptoSatUpsert(BaseModel):
    concepto: str
    clave_prodserv: str
    clave_unidad_sat: str | None = None


class CargaConceptosResponse(BaseModel):
    creados: int
    actualizados: int
    errores: list[dict]
    total_catalogo: int


@router.get("/conceptos", response_model=ConceptosPage)
def listar_conceptos(
    q: str | None = Query(default=None, max_length=120),
    limit: int = Query(default=200, le=2000),
    ctx: EmpresaContext = Depends(require_permissions("pedimentos.leer")),
    db: Session = Depends(get_db),
) -> ConceptosPage:
    """Catálogo concepto → clave SAT de la empresa (hoja CATALOGO del papel de trabajo)."""
    items, total = conceptos_mod.listar(db, empresa_id=ctx.empresa.id, q=q, limit=limit)
    return ConceptosPage(items=[ConceptoSatRead(id=c.id, concepto=c.concepto, clave_prodserv=c.clave_prodserv, clave_unidad_sat=c.clave_unidad_sat) for c in items], total=total)


@router.put("/conceptos", response_model=ConceptoSatRead)
def guardar_concepto(payload: ConceptoSatUpsert, ctx: EmpresaContext = Depends(require_permissions("pedimentos.gestionar")), db: Session = Depends(get_db)) -> ConceptoSatRead:
    if not (payload.clave_prodserv.isdigit() and len(payload.clave_prodserv) == 8):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "La clave SAT debe tener 8 dígitos")
    c, _ = conceptos_mod.upsert(db, empresa_id=ctx.empresa.id, concepto=payload.concepto, clave=payload.clave_prodserv, unidad=payload.clave_unidad_sat)
    db.commit()
    return ConceptoSatRead(id=c.id, concepto=c.concepto, clave_prodserv=c.clave_prodserv, clave_unidad_sat=c.clave_unidad_sat)


@router.get("/conceptos/plantilla", response_class=Response)
def plantilla_conceptos(ctx: EmpresaContext = Depends(require_permissions("pedimentos.leer"))) -> Response:
    return Response(content=conceptos_mod.plantilla(), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": 'attachment; filename="plantilla_conceptos_sat.xlsx"'})


@router.post("/conceptos/importar", response_model=CargaConceptosResponse)
async def importar_conceptos(
    archivo: UploadFile = File(...),
    ctx: EmpresaContext = Depends(require_permissions("pedimentos.gestionar")),
    db: Session = Depends(get_db),
) -> CargaConceptosResponse:
    """Carga masiva del catálogo concepto → clave SAT desde Excel/CSV (columnas: concepto, clave [, unidad])."""
    contenido = await archivo.read()
    try:
        r = conceptos_mod.importar_excel(db, empresa_id=ctx.empresa.id, contenido=contenido, nombre=archivo.filename or "")
    except ArchivoTabularError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    _, total = conceptos_mod.listar(db, empresa_id=ctx.empresa.id, limit=1)
    bitacora_crud.registrar(
        db, empresa_id=ctx.empresa.id, usuario=ctx.usuario, accion="pedimento.catalogo_conceptos",
        descripcion=f"Catálogo de conceptos → clave SAT: {r.creados} nuevos, {r.actualizados} actualizados, {len(r.errores)} con error",
        metadatos={"archivo": archivo.filename},
    )
    return CargaConceptosResponse(creados=r.creados, actualizados=r.actualizados, errores=r.errores, total_catalogo=total)


@router.post("/{pedimento_id}/aplicar-claves", response_model=PedimentoDetalleRead)
def aplicar_claves(pedimento_id: uuid.UUID, ctx: EmpresaContext = Depends(require_permissions("pedimentos.gestionar")), db: Session = Depends(get_db)) -> PedimentoDetalleRead:
    """Vuelve a buscar clave SAT para las partidas sin clave, usando el catálogo actual."""
    ped = _get_or_404(db, ctx, pedimento_id)
    try:
        crud._asegurar_editable(ped)
    except PedimentoAplicadoError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    conceptos_mod.aplicar_a_pedimento(db, pedimento=ped)
    db.commit()
    db.refresh(ped)
    return crud.a_detalle(ped)


@router.get("", response_model=list[PedimentoResumenRead])
def listar(
    estatus: str | None = Query(default=None, pattern="^(borrador|aplicado)$"),
    q: str | None = None,
    limit: int = Query(default=100, le=500),
    offset: int = 0,
    ctx: EmpresaContext = Depends(require_permissions("pedimentos.leer")),
    db: Session = Depends(get_db),
) -> list[PedimentoResumenRead]:
    return [crud.a_resumen(p) for p in crud.listar(db, empresa_id=ctx.empresa.id, estatus=estatus, q=q, limit=limit, offset=offset)]


@router.post("/importar", response_model=ImportarM3Response, status_code=status.HTTP_201_CREATED)
async def importar_m3(
    archivo: UploadFile = File(..., description="Archivo M3 del agente aduanal (.003 / .00N)"),
    referencia: str | None = Form(default=None),
    ctx: EmpresaContext = Depends(require_permissions("pedimentos.gestionar")),
    db: Session = Depends(get_db),
) -> ImportarM3Response:
    """Medio principal de captura: sube el archivo M3 y el pedimento queda
    registrado con todas sus partidas, impuestos y el costeo calculado."""
    contenido = await archivo.read()
    if len(contenido) > MAX_M3_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "El archivo es demasiado grande para ser un M3")
    try:
        m3 = parse_m3(contenido)
    except M3ParseError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"No se pudo leer el archivo: {exc}")

    advertencias: list[str] = []
    if m3.rfc_importador and m3.rfc_importador.upper() != ctx.empresa.rfc.upper():
        advertencias.append(
            f"El RFC importador del pedimento ({m3.rfc_importador}) no coincide con el de la empresa activa ({ctx.empresa.rfc})."
        )
    if m3.dta == 0:
        advertencias.append("El pedimento no trae DTA (registro 510); revisa si aplica capturarlo manualmente.")
    if m3.tipo_operacion and m3.tipo_operacion != "1":
        advertencias.append("El pedimento no es de importación (tipo de operación ≠ 1); el costeo está pensado para importaciones.")

    try:
        ped = crud.crear_desde_m3(
            db, empresa_id=ctx.empresa.id, m3=m3, archivo_nombre=(archivo.filename or "")[:120] or None, referencia=referencia
        )
    except PedimentoDuplicadoError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))

    sin_producto = sum(1 for p in ped.partidas if p.producto_id is None)
    if sin_producto:
        advertencias.append(
            f"{sin_producto} de {len(ped.partidas)} partidas no coinciden con ningún producto del catálogo; se crearán al aplicar al inventario (o asígnalos antes)."
        )

    bitacora_crud.registrar(
        db,
        empresa_id=ctx.empresa.id,
        usuario=ctx.usuario,
        accion="pedimento.importado",
        descripcion=f"Pedimento {ped.numero_completo} importado desde M3 ({len(ped.partidas)} partidas)",
        entidad_tipo="pedimento",
        entidad_id=ped.id,
        metadatos={"archivo": archivo.filename, "partidas": len(ped.partidas), "tipo_cambio": str(ped.tipo_cambio)},
    )
    return ImportarM3Response(pedimento=crud.a_detalle(ped), advertencias=advertencias)


@router.post("", response_model=PedimentoDetalleRead, status_code=status.HTTP_201_CREATED)
def crear_manual(
    payload: PedimentoCreate,
    ctx: EmpresaContext = Depends(require_permissions("pedimentos.gestionar")),
    db: Session = Depends(get_db),
) -> PedimentoDetalleRead:
    """Captura manual (respaldo cuando no se cuenta con el archivo M3)."""
    try:
        ped = crud.crear_manual(db, empresa_id=ctx.empresa.id, payload=payload)
    except PedimentoDuplicadoError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    bitacora_crud.registrar(
        db,
        empresa_id=ctx.empresa.id,
        usuario=ctx.usuario,
        accion="pedimento.creado",
        descripcion=f"Pedimento {ped.numero_completo} capturado manualmente ({len(ped.partidas)} partidas)",
        entidad_tipo="pedimento",
        entidad_id=ped.id,
    )
    return crud.a_detalle(ped)


@router.get("/{pedimento_id}", response_model=PedimentoDetalleRead)
def detalle(
    pedimento_id: uuid.UUID,
    ctx: EmpresaContext = Depends(require_permissions("pedimentos.leer")),
    db: Session = Depends(get_db),
) -> PedimentoDetalleRead:
    return crud.a_detalle(_get_or_404(db, ctx, pedimento_id))


@router.patch("/{pedimento_id}", response_model=PedimentoDetalleRead)
def actualizar(
    pedimento_id: uuid.UUID,
    payload: PedimentoUpdate,
    ctx: EmpresaContext = Depends(require_permissions("pedimentos.gestionar")),
    db: Session = Depends(get_db),
) -> PedimentoDetalleRead:
    """Cambia la configuración del costeo (gastos adicionales, utilidad, método
    de prorrateo, DTA) — el costeo se recalcula al vuelo."""
    ped = _get_or_404(db, ctx, pedimento_id)
    cambios = payload.model_dump(exclude_unset=True)
    try:
        ped = crud.actualizar(db, pedimento=ped, cambios=cambios)
    except PedimentoAplicadoError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    return crud.a_detalle(ped)


@router.patch("/{pedimento_id}/partidas/{partida_id}", response_model=PartidaRead)
def actualizar_partida(
    pedimento_id: uuid.UUID,
    partida_id: uuid.UUID,
    payload: PartidaUpdate,
    ctx: EmpresaContext = Depends(require_permissions("pedimentos.gestionar")),
    db: Session = Depends(get_db),
) -> PartidaRead:
    ped = _get_or_404(db, ctx, pedimento_id)
    partida = crud.get_partida(db, pedimento=ped, partida_id=partida_id)
    if partida is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Partida no encontrada")
    try:
        crud.actualizar_partida(db, pedimento=ped, partida=partida, cambios=payload.model_dump(exclude_unset=True))
    except PedimentoAplicadoError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    db.refresh(ped)
    detalle_ = crud.a_detalle(ped)
    return next(p for p in detalle_.partidas if p.id == partida_id)


@router.post("/{pedimento_id}/aplicar-inventario", response_model=AplicarInventarioResponse)
def aplicar_inventario(
    pedimento_id: uuid.UUID,
    payload: AplicarInventarioRequest,
    ctx: EmpresaContext = Depends(require_permissions("pedimentos.gestionar", "inventario.ajustar")),
    db: Session = Depends(get_db),
) -> AplicarInventarioResponse:
    """Da entrada al inventario: un movimiento por partida con su costo landed.
    Congela el pedimento."""
    ped = _get_or_404(db, ctx, pedimento_id)
    almacen = inventory_crud.get_almacen_por_codigo(db, empresa_id=ctx.empresa.id, codigo=payload.codigo_almacen)
    if almacen is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Almacén '{payload.codigo_almacen}' no encontrado")
    try:
        movimientos, productos, costo_total = crud.aplicar_inventario(
            db,
            pedimento=ped,
            almacen=almacen,
            crear_productos_faltantes=payload.crear_productos_faltantes,
            categoria_nuevos=payload.categoria_nuevos,
        )
    except (PedimentoAplicadoError, AplicarInventarioError) as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))

    bitacora_crud.registrar(
        db,
        empresa_id=ctx.empresa.id,
        usuario=ctx.usuario,
        accion="pedimento.aplicado",
        descripcion=(
            f"Pedimento {ped.numero_completo} aplicado al almacén {almacen.codigo}: "
            f"{movimientos} entradas, {productos} productos nuevos, costo ${costo_total:,.2f}"
        ),
        entidad_tipo="pedimento",
        entidad_id=ped.id,
        metadatos={"almacen": almacen.codigo, "movimientos": movimientos, "productos_creados": productos, "costo_total": str(costo_total)},
    )
    return AplicarInventarioResponse(
        pedimento_id=ped.id, movimientos_creados=movimientos, productos_creados=productos, costo_total=float(costo_total)
    )


@router.delete("/{pedimento_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar(
    pedimento_id: uuid.UUID,
    ctx: EmpresaContext = Depends(require_permissions("pedimentos.gestionar")),
    db: Session = Depends(get_db),
) -> None:
    ped = _get_or_404(db, ctx, pedimento_id)
    numero = ped.numero_completo
    try:
        crud.eliminar(db, pedimento=ped)
    except PedimentoAplicadoError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    bitacora_crud.registrar(
        db,
        empresa_id=ctx.empresa.id,
        usuario=ctx.usuario,
        accion="pedimento.eliminado",
        descripcion=f"Pedimento {numero} eliminado (borrador)",
        entidad_tipo="pedimento",
        entidad_id=pedimento_id,
    )
