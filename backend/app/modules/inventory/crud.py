import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.inventory.models import Almacen, Producto, StockMovimiento
from app.utils.money import to_money


class StockInsuficienteError(Exception):
    pass


def list_almacenes(db: Session, *, empresa_id: uuid.UUID) -> list[Almacen]:
    return list(
        db.scalars(select(Almacen).where(Almacen.empresa_id == empresa_id).order_by(Almacen.nombre))
    )


def get_almacen_por_codigo(db: Session, *, empresa_id: uuid.UUID, codigo: str) -> Almacen | None:
    return db.scalar(
        select(Almacen).where(Almacen.empresa_id == empresa_id, Almacen.codigo == codigo)
    )


def crear_almacen(db: Session, *, empresa_id: uuid.UUID, nombre: str, codigo: str) -> Almacen:
    almacen = Almacen(empresa_id=empresa_id, nombre=nombre, codigo=codigo)
    db.add(almacen)
    db.commit()
    db.refresh(almacen)
    return almacen


def list_productos(db: Session, *, empresa_id: uuid.UUID, categoria: str | None = None) -> list[Producto]:
    stmt = select(Producto).where(Producto.empresa_id == empresa_id)
    if categoria:
        stmt = stmt.where(Producto.categoria == categoria)
    return list(db.scalars(stmt.order_by(Producto.nombre)))


def list_categorias(db: Session, *, empresa_id: uuid.UUID) -> list[str]:
    """Categorías distintas ya usadas por la empresa, para poblar el filtro/autocompletar."""
    filas = db.scalars(
        select(Producto.categoria)
        .where(Producto.empresa_id == empresa_id, Producto.categoria.is_not(None))
        .distinct()
        .order_by(Producto.categoria)
    ).all()
    return list(filas)


def get_producto_por_sku(db: Session, *, empresa_id: uuid.UUID, sku: str) -> Producto | None:
    return db.scalar(select(Producto).where(Producto.empresa_id == empresa_id, Producto.sku == sku))


def crear_producto(
    db: Session,
    *,
    empresa_id: uuid.UUID,
    sku: str,
    nombre: str,
    tipo: str = "producto",
    categoria: str | None = None,
    unidad_codigo: str | None,
    costo_unitario: float,
    atributos: dict | None = None,
) -> Producto:
    producto = Producto(
        empresa_id=empresa_id,
        sku=sku,
        nombre=nombre,
        tipo=tipo,
        categoria=categoria,
        unidad_codigo=unidad_codigo,
        costo_unitario=to_money(costo_unitario),
        atributos=atributos,
    )
    db.add(producto)
    db.commit()
    db.refresh(producto)
    return producto


def disponible(db: Session, *, producto_id: uuid.UUID, almacen_id: uuid.UUID | None = None) -> int:
    stmt = select(func.coalesce(func.sum(StockMovimiento.cantidad), 0)).where(
        StockMovimiento.producto_id == producto_id
    )
    if almacen_id is not None:
        stmt = stmt.where(StockMovimiento.almacen_id == almacen_id)
    return int(db.scalar(stmt) or 0)


def stock_actual(db: Session, *, empresa_id: uuid.UUID) -> list[dict]:
    filas = db.execute(
        select(
            Producto.id,
            Producto.sku,
            Producto.nombre,
            Producto.categoria,
            Almacen.id,
            Almacen.codigo,
            func.coalesce(func.sum(StockMovimiento.cantidad), 0),
        )
        .select_from(StockMovimiento)
        .join(Producto, Producto.id == StockMovimiento.producto_id)
        .join(Almacen, Almacen.id == StockMovimiento.almacen_id)
        .where(StockMovimiento.empresa_id == empresa_id)
        .group_by(Producto.id, Producto.sku, Producto.nombre, Producto.categoria, Almacen.id, Almacen.codigo)
        .order_by(Producto.nombre)
    ).all()
    return [
        {
            "producto_id": pid,
            "sku": sku,
            "nombre_producto": nombre,
            "categoria": categoria,
            "almacen_id": aid,
            "codigo_almacen": codigo,
            "disponible": int(cant),
        }
        for pid, sku, nombre, categoria, aid, codigo, cant in filas
    ]


def list_movimientos(
    db: Session, *, empresa_id: uuid.UUID, limit: int = 100, offset: int = 0
) -> list[StockMovimiento]:
    return list(
        db.scalars(
            select(StockMovimiento)
            .where(StockMovimiento.empresa_id == empresa_id)
            .order_by(StockMovimiento.fecha.desc())
            .limit(limit)
            .offset(offset)
        )
    )


def registrar_movimiento(
    db: Session,
    *,
    empresa_id: uuid.UUID,
    producto: Producto,
    almacen: Almacen,
    tipo: str,
    cantidad: int,
    referencia: str | None = None,
    nota: str | None = None,
) -> StockMovimiento:
    if tipo in ("salida",) or (tipo == "ajuste" and cantidad < 0):
        actual = disponible(db, producto_id=producto.id, almacen_id=almacen.id)
        if actual + cantidad < 0:
            raise StockInsuficienteError(
                f"Stock insuficiente: disponible {actual}, se intentó mover {cantidad}"
            )

    movimiento = StockMovimiento(
        empresa_id=empresa_id,
        producto_id=producto.id,
        almacen_id=almacen.id,
        tipo=tipo,
        cantidad=cantidad,
        referencia=referencia,
        nota=nota,
    )
    db.add(movimiento)
    db.commit()
    db.refresh(movimiento)
    return movimiento
