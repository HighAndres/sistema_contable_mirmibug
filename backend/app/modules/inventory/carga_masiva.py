"""Carga masiva de inventario desde Excel/CSV: productos (alta/actualización por
SKU) y movimientos (entradas/salidas/ajustes). Cada fila se valida por separado y
los errores se devuelven con número de fila; las filas válidas SÍ se aplican."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy.orm import Session

from app.modules.inventory import crud
from app.modules.inventory.crud import StockInsuficienteError
from app.modules.inventory.models import Producto
from app.utils import tabular
from app.utils.money import to_money

SINONIMOS_PRODUCTOS = {
    "sku": ["sku", "clave", "codigo", "código", "clave interna", "id"],
    "nombre": ["nombre", "producto", "descripcion", "concepto"],
    "tipo": ["tipo"],
    "categoria": ["categoria", "familia", "linea", "grupo"],
    "unidad": ["unidad", "unidad codigo", "clave unidad", "claveunidad", "c_claveunidad", "um"],
    "costo": ["costo", "costo unitario", "costo_unitario", "precio costo", "precio"],
    "clave_sat": ["clave sat", "clave prodserv", "claveprodserv", "c_claveprodserv", "clave producto sat"],
    "activo": ["activo", "vigente"],
}
COLUMNAS_PRODUCTOS = ["SKU", "Nombre", "Tipo (producto/servicio)", "Categoría", "Unidad SAT", "Costo unitario", "Clave SAT", "Activo (si/no)"]

SINONIMOS_MOVIMIENTOS = {
    "sku": ["sku", "clave", "codigo", "código", "producto"],
    "almacen": ["almacen", "codigo almacen", "bodega", "sucursal"],
    "tipo": ["tipo", "movimiento", "tipo movimiento"],
    "cantidad": ["cantidad", "cant", "unidades", "piezas"],
    "costo": ["costo", "costo unitario", "costo_unitario"],
    "referencia": ["referencia", "ref", "documento", "folio"],
    "nota": ["nota", "notas", "observaciones", "comentario"],
}
COLUMNAS_MOVIMIENTOS = ["SKU", "Almacén (código)", "Tipo (entrada/salida/ajuste)", "Cantidad", "Costo unitario (opcional)", "Referencia", "Nota"]


@dataclass
class ResultadoCarga:
    creados: int = 0
    actualizados: int = 0
    errores: list[dict] = field(default_factory=list)


def _bool(v: object, default: bool = True) -> bool:
    if v is None:
        return default
    t = tabular.norm(v)
    if t in ("si", "sí", "s", "true", "1", "activo", "x", "yes"):
        return True
    if t in ("no", "n", "false", "0", "inactivo"):
        return False
    return default


def importar_productos(db: Session, *, empresa_id: uuid.UUID, contenido: bytes, nombre: str) -> ResultadoCarga:
    tabla = [r for r in tabular.leer_tabla(contenido, nombre) if r and any(v not in (None, "") for v in r)]
    idx, mapa = tabular.localizar_encabezado(tabla, SINONIMOS_PRODUCTOS, {"sku", "nombre"})
    # Columnas que no reconocemos se guardan como atributos libres del producto.
    encabezado = tabla[idx]
    extras = {i: str(h).strip() for i, h in enumerate(encabezado) if h not in (None, "") and i not in mapa.values()}
    res = ResultadoCarga()
    vistos: set[str] = set()
    for n, fila in enumerate(tabla[idx + 1 :], start=idx + 2):
        sku = tabular.texto(tabular.celda(fila, mapa, "sku"))
        nombre_p = tabular.texto(tabular.celda(fila, mapa, "nombre"))
        if not sku and not nombre_p:
            continue
        if not sku or not nombre_p:
            res.errores.append({"fila": n, "sku": sku, "error": "SKU y nombre son obligatorios"})
            continue
        if sku.upper() in vistos:
            res.errores.append({"fila": n, "sku": sku, "error": "SKU repetido en el archivo"})
            continue
        vistos.add(sku.upper())
        tipo = (tabular.texto(tabular.celda(fila, mapa, "tipo")) or "producto").lower()
        if tipo not in ("producto", "servicio"):
            res.errores.append({"fila": n, "sku": sku, "error": f"Tipo inválido '{tipo}' (producto | servicio)"})
            continue
        costo_raw = tabular.celda(fila, mapa, "costo")
        costo = tabular.a_decimal(costo_raw) if costo_raw is not None else Decimal("0")
        if costo is None or costo < 0:
            res.errores.append({"fila": n, "sku": sku, "error": f"Costo inválido: {costo_raw!r}"})
            continue
        clave_raw = tabular.celda(fila, mapa, "clave_sat")
        clave = tabular.texto(int(clave_raw) if isinstance(clave_raw, float) and clave_raw.is_integer() else clave_raw)
        if clave and (not clave.isdigit() or len(clave) != 8):
            res.errores.append({"fila": n, "sku": sku, "error": f"Clave SAT inválida: {clave!r} (8 dígitos)"})
            continue
        atributos = {}
        for i, h in extras.items():
            v = fila[i] if i < len(fila) else None
            if v not in (None, ""):
                atributos[h] = v if isinstance(v, (int, float)) else str(v).strip()

        prod = crud.get_producto_por_sku(db, empresa_id=empresa_id, sku=sku)
        if prod is None:
            prod = Producto(empresa_id=empresa_id, sku=sku[:64])
            db.add(prod)
            res.creados += 1
        else:
            res.actualizados += 1
        prod.nombre = nombre_p[:255]
        prod.tipo = tipo
        prod.categoria = (tabular.texto(tabular.celda(fila, mapa, "categoria")) or None)
        prod.unidad_codigo = tabular.texto(tabular.celda(fila, mapa, "unidad"))
        prod.costo_unitario = to_money(costo)
        prod.clave_prodserv = clave
        prod.activo = _bool(tabular.celda(fila, mapa, "activo"), True)
        if atributos:
            prod.atributos = {**(prod.atributos or {}), **atributos}
    db.commit()
    return res


def importar_movimientos(db: Session, *, empresa_id: uuid.UUID, contenido: bytes, nombre: str) -> ResultadoCarga:
    tabla = [r for r in tabular.leer_tabla(contenido, nombre) if r and any(v not in (None, "") for v in r)]
    idx, mapa = tabular.localizar_encabezado(tabla, SINONIMOS_MOVIMIENTOS, {"sku", "almacen", "tipo", "cantidad"})
    res = ResultadoCarga()
    for n, fila in enumerate(tabla[idx + 1 :], start=idx + 2):
        sku = tabular.texto(tabular.celda(fila, mapa, "sku"))
        cod_alm = tabular.texto(tabular.celda(fila, mapa, "almacen"))
        tipo = (tabular.texto(tabular.celda(fila, mapa, "tipo")) or "").lower()
        cant_raw = tabular.celda(fila, mapa, "cantidad")
        if not any((sku, cod_alm, cant_raw)):
            continue
        cant = tabular.a_decimal(cant_raw)
        if tipo not in ("entrada", "salida", "ajuste"):
            res.errores.append({"fila": n, "sku": sku, "error": f"Tipo inválido '{tipo}' (entrada | salida | ajuste)"})
            continue
        if cant is None or cant == 0 or cant != cant.to_integral_value():
            res.errores.append({"fila": n, "sku": sku, "error": f"Cantidad inválida: {cant_raw!r} (entero distinto de 0)"})
            continue
        cantidad = int(cant)
        if tipo == "entrada":
            cantidad = abs(cantidad)
        elif tipo == "salida":
            cantidad = -abs(cantidad)
        producto = crud.get_producto_por_sku(db, empresa_id=empresa_id, sku=sku or "")
        if producto is None:
            res.errores.append({"fila": n, "sku": sku, "error": f"Producto '{sku}' no existe"})
            continue
        almacen = crud.get_almacen_por_codigo(db, empresa_id=empresa_id, codigo=cod_alm or "")
        if almacen is None:
            res.errores.append({"fila": n, "sku": sku, "error": f"Almacén '{cod_alm}' no existe"})
            continue
        costo_raw = tabular.celda(fila, mapa, "costo")
        costo = tabular.a_decimal(costo_raw) if costo_raw not in (None, "") else None
        try:
            mov = crud.registrar_movimiento(
                db, empresa_id=empresa_id, producto=producto, almacen=almacen, tipo=tipo, cantidad=cantidad,
                referencia=tabular.texto(tabular.celda(fila, mapa, "referencia")),
                nota=tabular.texto(tabular.celda(fila, mapa, "nota")),
            )
            if costo is not None:
                mov.costo_unitario = costo
                db.commit()
            res.creados += 1
        except StockInsuficienteError as exc:
            res.errores.append({"fila": n, "sku": sku, "error": str(exc)})
    return res


def plantilla_productos() -> bytes:
    return tabular.plantilla_xlsx(
        "Productos", COLUMNAS_PRODUCTOS,
        ["LAP-001", "Laptop 14 pulgadas", "producto", "Cómputo", "H87", 12500, "43211503", "si"],
        [
            "SKU y Nombre son obligatorios. Si el SKU ya existe, el producto se actualiza; si no, se crea.",
            "Tipo: producto (controla existencias) o servicio. Unidad SAT: c_ClaveUnidad (H87 pieza, E48 servicio, KGM kilo...).",
            "Clave SAT: 8 dígitos de c_ClaveProdServ (opcional). Costo unitario en MXN.",
            "Cualquier columna adicional (p. ej. Color, Talla, Marca) se guarda como atributo libre del producto.",
        ],
    )


def plantilla_movimientos() -> bytes:
    return tabular.plantilla_xlsx(
        "Movimientos", COLUMNAS_MOVIMIENTOS,
        ["LAP-001", "CENTRAL", "entrada", 10, 12500, "OC-2026-001", "Compra inicial"],
        [
            "El producto (SKU) y el almacén (código) deben existir. Tipo: entrada, salida o ajuste.",
            "Cantidad: entero; para salidas se toma como positivo y el sistema le pone el signo. Ajuste: con signo (+/−).",
            "Una salida que deje el stock negativo se rechaza y se reporta en esa fila; las demás filas sí se aplican.",
        ],
    )
