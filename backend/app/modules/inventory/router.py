from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import EmpresaContext, require_permissions
from app.db.session import get_db
from app.modules.bitacora import crud as bitacora_crud
from app.modules.inventory import crud
from app.modules.inventory.crud import StockInsuficienteError
from app.modules.inventory.schemas import (
    AlmacenCreate,
    AlmacenRead,
    MovimientoCreate,
    MovimientoRead,
    ProductoCreate,
    ProductoRead,
    StockItem,
)

router = APIRouter(prefix="/inventory", tags=["inventory"])


def _validar_signo(tipo: str, cantidad: int) -> None:
    if cantidad == 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "La cantidad no puede ser 0")
    if tipo == "entrada" and cantidad < 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Una entrada debe ser positiva")
    if tipo == "salida" and cantidad > 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Una salida debe ser negativa")


@router.get("/almacenes", response_model=list[AlmacenRead])
def listar_almacenes(
    ctx: EmpresaContext = Depends(require_permissions("inventario.leer")),
    db: Session = Depends(get_db),
) -> list[AlmacenRead]:
    return crud.list_almacenes(db, empresa_id=ctx.empresa.id)


@router.post("/almacenes", response_model=AlmacenRead, status_code=status.HTTP_201_CREATED)
def crear_almacen(
    payload: AlmacenCreate,
    ctx: EmpresaContext = Depends(require_permissions("inventario.ajustar")),
    db: Session = Depends(get_db),
) -> AlmacenRead:
    almacen = crud.crear_almacen(db, empresa_id=ctx.empresa.id, nombre=payload.nombre, codigo=payload.codigo)
    bitacora_crud.registrar(
        db,
        empresa_id=ctx.empresa.id,
        usuario=ctx.usuario,
        accion="inventario.almacen_creado",
        descripcion=f"Almacén '{almacen.nombre}' ({almacen.codigo}) creado",
        entidad_tipo="almacen",
        entidad_id=almacen.id,
    )
    return almacen


@router.get("/productos", response_model=list[ProductoRead])
def listar_productos(
    categoria: str | None = None,
    ctx: EmpresaContext = Depends(require_permissions("inventario.leer")),
    db: Session = Depends(get_db),
) -> list[ProductoRead]:
    return crud.list_productos(db, empresa_id=ctx.empresa.id, categoria=categoria)


@router.get("/categorias", response_model=list[str])
def listar_categorias(
    ctx: EmpresaContext = Depends(require_permissions("inventario.leer")),
    db: Session = Depends(get_db),
) -> list[str]:
    return crud.list_categorias(db, empresa_id=ctx.empresa.id)


@router.post("/productos", response_model=ProductoRead, status_code=status.HTTP_201_CREATED)
def crear_producto(
    payload: ProductoCreate,
    ctx: EmpresaContext = Depends(require_permissions("inventario.ajustar")),
    db: Session = Depends(get_db),
) -> ProductoRead:
    producto = crud.crear_producto(
        db,
        empresa_id=ctx.empresa.id,
        sku=payload.sku,
        nombre=payload.nombre,
        tipo=payload.tipo,
        categoria=payload.categoria,
        unidad_codigo=payload.unidad_codigo,
        costo_unitario=payload.costo_unitario,
        atributos=payload.atributos,
    )
    bitacora_crud.registrar(
        db,
        empresa_id=ctx.empresa.id,
        usuario=ctx.usuario,
        accion="inventario.producto_creado",
        descripcion=f"Producto '{producto.nombre}' ({producto.sku}) creado",
        entidad_tipo="producto",
        entidad_id=producto.id,
    )
    return producto


@router.get("/stock", response_model=list[StockItem])
def stock_actual(
    ctx: EmpresaContext = Depends(require_permissions("inventario.leer")),
    db: Session = Depends(get_db),
) -> list[StockItem]:
    return crud.stock_actual(db, empresa_id=ctx.empresa.id)


@router.get("/movimientos", response_model=list[MovimientoRead])
def listar_movimientos(
    limit: int = 100,
    offset: int = 0,
    ctx: EmpresaContext = Depends(require_permissions("inventario.leer")),
    db: Session = Depends(get_db),
) -> list[MovimientoRead]:
    movimientos = crud.list_movimientos(db, empresa_id=ctx.empresa.id, limit=limit, offset=offset)
    return [MovimientoRead.from_orm_model(m) for m in movimientos]


@router.post("/movimientos", response_model=MovimientoRead, status_code=status.HTTP_201_CREATED)
def registrar_movimiento(
    payload: MovimientoCreate,
    ctx: EmpresaContext = Depends(require_permissions("inventario.ajustar")),
    db: Session = Depends(get_db),
) -> MovimientoRead:
    _validar_signo(payload.tipo, payload.cantidad)

    producto = crud.get_producto_por_sku(db, empresa_id=ctx.empresa.id, sku=payload.sku)
    if producto is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Producto con SKU '{payload.sku}' no encontrado")

    almacen = crud.get_almacen_por_codigo(db, empresa_id=ctx.empresa.id, codigo=payload.codigo_almacen)
    if almacen is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, f"Almacén '{payload.codigo_almacen}' no encontrado"
        )

    try:
        movimiento = crud.registrar_movimiento(
            db,
            empresa_id=ctx.empresa.id,
            producto=producto,
            almacen=almacen,
            tipo=payload.tipo,
            cantidad=payload.cantidad,
            referencia=payload.referencia,
            nota=payload.nota,
        )
    except StockInsuficienteError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))

    bitacora_crud.registrar(
        db,
        empresa_id=ctx.empresa.id,
        usuario=ctx.usuario,
        accion="inventario.movimiento",
        descripcion=(
            f"Movimiento de {producto.sku} en {almacen.codigo}: {payload.tipo} de {payload.cantidad} unidades"
        ),
        entidad_tipo="stock_movimiento",
        entidad_id=movimiento.id,
        metadatos={"sku": producto.sku, "tipo": payload.tipo, "cantidad": payload.cantidad},
    )
    return MovimientoRead.from_orm_model(movimiento)
