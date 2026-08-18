import re
import uuid
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.inventory.models import Almacen, Producto, StockMovimiento
from app.modules.pedimentos import conceptos as conceptos_mod
from app.modules.pedimentos import costeo as costeo_mod
from app.modules.pedimentos.models import Pedimento, PedimentoPartida
from app.modules.pedimentos.parser_m3 import PedimentoM3
from app.modules.pedimentos.schemas import (
    CosteoResumenRead,
    GastoAdicional,
    PartidaCosteoRead,
    PartidaRead,
    PedimentoCreate,
    PedimentoDetalleRead,
    PedimentoResumenRead,
)
from app.modules.pedimentos.umc import umc_clave_sat, umc_descripcion


class PedimentoDuplicadoError(Exception):
    pass


class PedimentoAplicadoError(Exception):
    """Un pedimento ya aplicado al inventario está congelado."""


class AplicarInventarioError(Exception):
    pass


# ---------- Consultas ----------


def get(db: Session, *, empresa_id: uuid.UUID, pedimento_id: uuid.UUID) -> Pedimento | None:
    return db.scalar(select(Pedimento).where(Pedimento.id == pedimento_id, Pedimento.empresa_id == empresa_id))


def get_por_clave(db: Session, *, empresa_id: uuid.UUID, aduana: str, patente: str, numero: str) -> Pedimento | None:
    return db.scalar(
        select(Pedimento).where(
            Pedimento.empresa_id == empresa_id,
            Pedimento.aduana == aduana,
            Pedimento.patente == patente,
            Pedimento.numero == numero,
        )
    )


def listar(
    db: Session, *, empresa_id: uuid.UUID, estatus: str | None = None, q: str | None = None, limit: int = 100, offset: int = 0
) -> list[Pedimento]:
    stmt = select(Pedimento).where(Pedimento.empresa_id == empresa_id)
    if estatus:
        stmt = stmt.where(Pedimento.estatus == estatus)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            Pedimento.numero.ilike(like)
            | Pedimento.referencia.ilike(like)
            | Pedimento.proveedor_nombre.ilike(like)
        )
    return list(db.scalars(stmt.order_by(Pedimento.fecha_pago.desc().nulls_last(), Pedimento.created_at.desc()).limit(limit).offset(offset)))


def get_partida(db: Session, *, pedimento: Pedimento, partida_id: uuid.UUID) -> PedimentoPartida | None:
    return next((p for p in pedimento.partidas if p.id == partida_id), None)


# ---------- Alta ----------


def crear_desde_m3(
    db: Session, *, empresa_id: uuid.UUID, m3: PedimentoM3, archivo_nombre: str | None = None, referencia: str | None = None
) -> Pedimento:
    if get_por_clave(db, empresa_id=empresa_id, aduana=m3.aduana, patente=m3.patente, numero=m3.numero):
        raise PedimentoDuplicadoError(f"El pedimento {m3.numero_completo} ya está registrado en esta empresa")

    ped = Pedimento(
        empresa_id=empresa_id,
        numero=m3.numero,
        patente=m3.patente,
        aduana=m3.aduana,
        clave_pedimento=m3.clave_pedimento,
        tipo_operacion=m3.tipo_operacion,
        rfc_importador=m3.rfc_importador,
        referencia=referencia,
        fecha_entrada=m3.fecha_entrada,
        fecha_pago=m3.fecha_pago,
        tipo_cambio=m3.tipo_cambio,
        peso_bruto=m3.peso_bruto,
        incoterm=m3.incoterm,
        proveedor_nombre=m3.proveedor_nombre,
        proveedor_id_fiscal=m3.proveedor_id_fiscal,
        contenedores=m3.contenedores or None,
        guias=m3.guias or None,
        dta=m3.dta,
        otras_contribuciones=m3.otras_contribuciones or None,
        gastos_adicionales=[],
        utilidad=Decimal("0"),
        origen="m3",
        archivo_nombre=archivo_nombre,
    )
    for p in m3.partidas:
        ped.partidas.append(
            PedimentoPartida(
                secuencia=p.secuencia,
                fraccion=p.fraccion,
                nico=p.nico,
                descripcion=p.descripcion[:255],
                pais_origen=p.pais_origen,
                cantidad_umc=p.cantidad_umc,
                umc_clave=p.umc_clave,
                cantidad_umt=p.cantidad_umt,
                umt_clave=p.umt_clave,
                precio_unitario=p.precio_unitario,
                valor_aduana=p.valor_aduana,
                valor_comercial=p.valor_comercial,
                valor_usd=p.valor_usd,
                igi=p.igi,
                iva=p.iva,
                tasa_igi=p.tasa_igi,
                tasa_iva=p.tasa_iva,
                clave_unidad_sat=umc_clave_sat(p.umc_clave),
            )
        )
    _sugerir_productos(db, empresa_id=empresa_id, pedimento=ped)
    db.add(ped)
    db.commit()
    db.refresh(ped)
    return ped


def crear_manual(db: Session, *, empresa_id: uuid.UUID, payload: PedimentoCreate) -> Pedimento:
    if get_por_clave(db, empresa_id=empresa_id, aduana=payload.aduana, patente=payload.patente, numero=payload.numero):
        raise PedimentoDuplicadoError(f"El pedimento {payload.aduana}/{payload.patente}/{payload.numero} ya está registrado")

    datos = payload.model_dump(exclude={"partidas", "gastos_adicionales"})
    ped = Pedimento(
        empresa_id=empresa_id,
        origen="manual",
        gastos_adicionales=[g.model_dump(mode="json") for g in payload.gastos_adicionales],
        **datos,
    )
    for p in payload.partidas:
        d = p.model_dump()
        d["valor_comercial"] = d["valor_comercial"] if d["valor_comercial"] is not None else d["valor_aduana"]
        d["valor_usd"] = d["valor_usd"] if d["valor_usd"] is not None else (
            Decimal(d["valor_aduana"]) / Decimal(payload.tipo_cambio)
        ).quantize(Decimal("0.01"))
        if not d.get("clave_unidad_sat"):
            d["clave_unidad_sat"] = umc_clave_sat(d["umc_clave"])
        ped.partidas.append(PedimentoPartida(**d))
    _sugerir_productos(db, empresa_id=empresa_id, pedimento=ped)
    db.add(ped)
    db.commit()
    db.refresh(ped)
    return ped


def _sugerir_productos(db: Session, *, empresa_id: uuid.UUID, pedimento: Pedimento) -> None:
    """Si ya existe un producto con el mismo nombre en la empresa, lo liga de una
    vez (y hereda su clave SAT). Es el equivalente al VLOOKUP contra la hoja
    CATALOGO del Excel, pero sin '#N/A': lo que no se encuentre queda vacío y
    se resuelve al aplicar."""
    nombres = {p.descripcion.strip().upper() for p in pedimento.partidas}
    if not nombres:
        return
    existentes = db.scalars(
        select(Producto).where(Producto.empresa_id == empresa_id, func.upper(Producto.nombre).in_(nombres))
    ).all()
    por_nombre = {pr.nombre.strip().upper(): pr for pr in existentes}
    for part in pedimento.partidas:
        pr = por_nombre.get(part.descripcion.strip().upper())
        if pr is not None:
            part.producto_id = pr.id
            if not part.clave_prodserv and pr.clave_prodserv:
                part.clave_prodserv = pr.clave_prodserv
    # Y el catálogo concepto → clave SAT de la empresa (hoja CATALOGO del Excel).
    conceptos_mod.aplicar_a_pedimento(db, pedimento=pedimento)


# ---------- Edición ----------


def _asegurar_editable(ped: Pedimento) -> None:
    if ped.estatus == "aplicado":
        raise PedimentoAplicadoError("El pedimento ya fue aplicado al inventario y no se puede modificar")


def actualizar(db: Session, *, pedimento: Pedimento, cambios: dict) -> Pedimento:
    _asegurar_editable(pedimento)
    if "gastos_adicionales" in cambios and cambios["gastos_adicionales"] is not None:
        cambios["gastos_adicionales"] = [
            (g.model_dump(mode="json") if isinstance(g, GastoAdicional) else g) for g in cambios["gastos_adicionales"]
        ]
    for k, v in cambios.items():
        setattr(pedimento, k, v)
    db.commit()
    db.refresh(pedimento)
    return pedimento


def actualizar_partida(db: Session, *, pedimento: Pedimento, partida: PedimentoPartida, cambios: dict) -> PedimentoPartida:
    _asegurar_editable(pedimento)
    if "producto_id" in cambios and cambios["producto_id"] is not None:
        prod = db.scalar(select(Producto).where(Producto.id == cambios["producto_id"], Producto.empresa_id == pedimento.empresa_id))
        if prod is None:
            raise ValueError("El producto no existe en esta empresa")
    for k, v in cambios.items():
        setattr(partida, k, v)
    db.commit()
    db.refresh(partida)
    return partida


def eliminar(db: Session, *, pedimento: Pedimento) -> None:
    _asegurar_editable(pedimento)
    db.delete(pedimento)
    db.commit()


# ---------- Costeo ----------


def total_gastos(pedimento: Pedimento) -> Decimal:
    return sum((Decimal(str(g.get("monto", 0))) for g in (pedimento.gastos_adicionales or [])), Decimal("0"))


def costear(pedimento: Pedimento) -> costeo_mod.CosteoPedimento:
    return costeo_mod.costear(
        pedimento.partidas,
        dta=Decimal(pedimento.dta or 0),
        gastos_adicionales=total_gastos(pedimento),
        utilidad=Decimal(pedimento.utilidad or 0),
        metodo_prorrateo=pedimento.metodo_prorrateo,
    )


# ---------- Aplicar al inventario ----------


def _slug_sku(texto: str, maximo: int = 40) -> str:
    base = re.sub(r"[^A-Z0-9]+", "-", texto.upper()).strip("-")
    return (base or "PARTIDA")[:maximo]


def _sku_unico(db: Session, *, empresa_id: uuid.UUID, base: str) -> str:
    sku, i = base, 2
    while db.scalar(select(Producto.id).where(Producto.empresa_id == empresa_id, Producto.sku == sku)):
        sku = f"{base}-{i}"
        i += 1
    return sku


def aplicar_inventario(
    db: Session,
    *,
    pedimento: Pedimento,
    almacen: Almacen,
    crear_productos_faltantes: bool = True,
    categoria_nuevos: str | None = "Importación",
) -> tuple[int, int, Decimal]:
    """Genera una ENTRADA al ledger por partida con su costo unitario landed.
    Devuelve (movimientos_creados, productos_creados, costo_total)."""
    _asegurar_editable(pedimento)

    # El ledger cuenta enteros: una partida en kilos con decimales no puede entrar tal cual.
    no_enteras = [p.secuencia for p in pedimento.partidas if Decimal(p.cantidad_umc) != Decimal(p.cantidad_umc).to_integral_value()]
    if no_enteras:
        raise AplicarInventarioError(
            f"Las partidas {no_enteras} tienen cantidad con decimales; el inventario maneja unidades enteras"
        )
    sin_producto = [p for p in pedimento.partidas if p.producto_id is None]
    if sin_producto and not crear_productos_faltantes:
        raise AplicarInventarioError(
            f"Las partidas {[p.secuencia for p in sin_producto]} no tienen producto asignado"
        )

    resultado = costear(pedimento)
    por_secuencia = {r.secuencia: r for r in resultado.partidas}

    productos_creados = 0
    movimientos = 0
    # Dos partidas del mismo pedimento con la misma descripción (p. ej. distinta
    # fracción/NICO) entran al mismo producto, no a dos.
    creados_por_nombre: dict[str, Producto] = {}
    for part in pedimento.partidas:
        r = por_secuencia[part.secuencia]
        nombre_norm = part.descripcion.strip().upper()
        if part.producto_id is None and nombre_norm in creados_por_nombre:
            part.producto_id = creados_por_nombre[nombre_norm].id
            db.flush()
            db.refresh(part)
        if part.producto_id is None:
            sku = _sku_unico(db, empresa_id=pedimento.empresa_id, base=_slug_sku(part.descripcion))
            prod = Producto(
                empresa_id=pedimento.empresa_id,
                sku=sku,
                nombre=part.descripcion,
                tipo="producto",
                categoria=categoria_nuevos,
                unidad_codigo=part.clave_unidad_sat or umc_clave_sat(part.umc_clave),
                costo_unitario=r.costo_unitario.quantize(Decimal("0.01")),
                clave_prodserv=part.clave_prodserv,
                atributos={"fraccion_arancelaria": part.fraccion, "pais_origen": part.pais_origen},
            )
            db.add(prod)
            db.flush()
            part.producto_id = prod.id
            creados_por_nombre[nombre_norm] = prod
            productos_creados += 1
        else:
            prod = part.producto
            # Último costo conocido: el de esta importación.
            prod.costo_unitario = r.costo_unitario.quantize(Decimal("0.01"))
            if part.clave_prodserv and not prod.clave_prodserv:
                prod.clave_prodserv = part.clave_prodserv

        db.add(
            StockMovimiento(
                empresa_id=pedimento.empresa_id,
                producto_id=part.producto_id,
                almacen_id=almacen.id,
                tipo="entrada",
                cantidad=int(Decimal(part.cantidad_umc)),
                referencia=f"PED {pedimento.numero_completo}",
                nota=f"Partida {part.secuencia} · {part.descripcion}"[:255],
                costo_unitario=r.costo_unitario,
            )
        )
        movimientos += 1

    pedimento.estatus = "aplicado"
    pedimento.aplicado_almacen_id = almacen.id
    db.commit()
    db.refresh(pedimento)
    return movimientos, productos_creados, resultado.costo_total


# ---------- Serialización ----------


def a_resumen(ped: Pedimento) -> PedimentoResumenRead:
    return PedimentoResumenRead(
        id=ped.id,
        numero_completo=ped.numero_completo,
        numero=ped.numero,
        patente=ped.patente,
        aduana=ped.aduana,
        clave_pedimento=ped.clave_pedimento,
        referencia=ped.referencia,
        fecha_pago=ped.fecha_pago,
        tipo_cambio=float(ped.tipo_cambio),
        proveedor_nombre=ped.proveedor_nombre,
        num_partidas=len(ped.partidas),
        valor_aduana_total=float(sum((Decimal(p.valor_aduana) for p in ped.partidas), Decimal("0"))),
        dta=float(ped.dta or 0),
        igi_total=float(sum((Decimal(p.igi) for p in ped.partidas), Decimal("0"))),
        iva_total=float(sum((Decimal(p.iva) for p in ped.partidas), Decimal("0"))),
        estatus=ped.estatus,
        origen=ped.origen,
        created_at=ped.created_at,
    )


def a_detalle(ped: Pedimento) -> PedimentoDetalleRead:
    resultado = costear(ped)
    por_secuencia = {r.secuencia: r for r in resultado.partidas}
    resumen = a_resumen(ped)
    partidas = []
    for p in ped.partidas:
        r = por_secuencia[p.secuencia]
        partidas.append(
            PartidaRead(
                id=p.id,
                secuencia=p.secuencia,
                fraccion=p.fraccion,
                nico=p.nico,
                descripcion=p.descripcion,
                pais_origen=p.pais_origen,
                cantidad_umc=float(p.cantidad_umc),
                umc_clave=p.umc_clave,
                umc_descripcion=umc_descripcion(p.umc_clave),
                cantidad_umt=float(p.cantidad_umt) if p.cantidad_umt is not None else None,
                umt_clave=p.umt_clave,
                precio_unitario=float(p.precio_unitario),
                valor_aduana=float(p.valor_aduana),
                valor_comercial=float(p.valor_comercial),
                valor_usd=float(p.valor_usd),
                igi=float(p.igi),
                iva=float(p.iva),
                tasa_igi=float(p.tasa_igi) if p.tasa_igi is not None else None,
                tasa_iva=float(p.tasa_iva) if p.tasa_iva is not None else None,
                clave_prodserv=p.clave_prodserv,
                clave_unidad_sat=p.clave_unidad_sat,
                producto_id=p.producto_id,
                producto_sku=p.producto.sku if p.producto is not None else None,
                costeo=PartidaCosteoRead(
                    dta_asignado=float(r.dta_asignado),
                    dta_pza=float(r.dta_pza),
                    igi_pza=float(r.igi_pza),
                    gastos_asignados=float(r.gastos_asignados),
                    gastos_pza=float(r.gastos_pza),
                    utilidad_asignada=float(r.utilidad_asignada),
                    utilidad_pza=float(r.utilidad_pza),
                    costo_unitario=float(r.costo_unitario),
                    precio_unitario_venta=float(r.precio_unitario_venta),
                    subtotal=float(r.subtotal),
                    iva_16=float(r.iva_16),
                    total=float(r.total),
                    dif_iva=float(r.dif_iva),
                ),
            )
        )
    return PedimentoDetalleRead(
        **resumen.model_dump(),
        tipo_operacion=ped.tipo_operacion,
        rfc_importador=ped.rfc_importador,
        fecha_entrada=ped.fecha_entrada,
        peso_bruto=float(ped.peso_bruto) if ped.peso_bruto is not None else None,
        incoterm=ped.incoterm,
        proveedor_id_fiscal=ped.proveedor_id_fiscal,
        contenedores=ped.contenedores,
        guias=ped.guias,
        otras_contribuciones=ped.otras_contribuciones,
        gastos_adicionales=[GastoAdicional(**g) for g in (ped.gastos_adicionales or [])],
        utilidad=float(ped.utilidad or 0),
        metodo_prorrateo=ped.metodo_prorrateo,
        aplicado_almacen_id=ped.aplicado_almacen_id,
        archivo_nombre=ped.archivo_nombre,
        notas=ped.notas,
        valor_usd_total=float(sum((Decimal(p.valor_usd) for p in ped.partidas), Decimal("0"))),
        resumen=CosteoResumenRead(
            dta=float(resultado.dta),
            gastos_adicionales=float(resultado.gastos_adicionales),
            utilidad=float(resultado.utilidad),
            igi_total=float(resultado.igi_total),
            iva_importacion_total=float(resultado.iva_importacion_total),
            costo_total=float(resultado.costo_total),
            subtotal_venta=float(resultado.subtotal_venta),
            iva_venta=float(resultado.iva_venta),
            total_venta=float(resultado.total_venta),
            dif_iva_total=float(resultado.dif_iva_total),
        ),
        partidas=partidas,
    )
