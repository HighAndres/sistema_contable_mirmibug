import uuid
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from app.modules.cfdi.models import Cfdi
from app.modules.impuestos import crud as impuestos_crud
from app.modules.rules.engine import RFCS_EFOS_MOCK
from app.modules.terceros.models import Tercero
from app.modules.terceros.schemas import Antiguedad, TerceroDetalleRead, TerceroResumenRead
from app.utils import tabular


# ---------- CRUD ----------


def get(db: Session, *, empresa_id: uuid.UUID, tercero_id: uuid.UUID) -> Tercero | None:
    return db.scalar(select(Tercero).where(Tercero.id == tercero_id, Tercero.empresa_id == empresa_id))


def get_por_rfc(db: Session, *, empresa_id: uuid.UUID, rfc: str) -> Tercero | None:
    return db.scalar(select(Tercero).where(Tercero.empresa_id == empresa_id, Tercero.rfc == rfc.strip().upper()))


def listar(db: Session, *, empresa_id: uuid.UUID, tipo: str | None = None, q: str | None = None, activo: bool | None = None) -> list[Tercero]:
    stmt = select(Tercero).where(Tercero.empresa_id == empresa_id)
    if tipo in ("cliente", "proveedor"):
        stmt = stmt.where(Tercero.tipo.in_((tipo, "ambos")))
    if activo is not None:
        stmt = stmt.where(Tercero.activo == activo)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Tercero.rfc.ilike(like), Tercero.nombre.ilike(like), Tercero.contacto.ilike(like), Tercero.email.ilike(like)))
    return list(db.scalars(stmt.order_by(Tercero.nombre)))


def crear(db: Session, *, empresa_id: uuid.UUID, origen: str = "manual", **datos) -> Tercero:
    t = Tercero(empresa_id=empresa_id, origen=origen, **datos)
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


def actualizar(db: Session, *, tercero: Tercero, cambios: dict) -> Tercero:
    for k, v in cambios.items():
        setattr(tercero, k, v)
    db.commit()
    db.refresh(tercero)
    return tercero


# ---------- Desde la bóveda ----------


def sincronizar_desde_cfdi(db: Session, *, empresa_id: uuid.UUID) -> tuple[int, int]:
    """Crea/actualiza terceros con las contrapartes de los CFDI (ingresos → clientes,
    gastos → proveedores; nómina y ajenos no). El nombre se toma del CFDI más reciente."""
    filas = db.execute(
        select(
            case((Cfdi.direccion == "emitido", Cfdi.rfc_receptor), else_=Cfdi.rfc_emisor).label("rfc"),
            case((Cfdi.direccion == "emitido", Cfdi.nombre_receptor), else_=Cfdi.nombre_emisor).label("nombre"),
            Cfdi.direccion,
            func.max(Cfdi.fecha),
        )
        .where(Cfdi.empresa_id == empresa_id, Cfdi.tipo.in_(("ingreso", "egreso", "pago", "nota_credito")))
        .group_by("rfc", "nombre", Cfdi.direccion)
    ).all()
    # rfc → {"cliente"|"proveedor"} y nombre más reciente
    roles: dict[str, set[str]] = {}
    nombres: dict[str, tuple[date, str]] = {}
    for rfc, nombre, direccion, ult in filas:
        if not rfc:
            continue
        roles.setdefault(rfc, set()).add("cliente" if direccion == "emitido" else "proveedor")
        if rfc not in nombres or ult > nombres[rfc][0]:
            nombres[rfc] = (ult, nombre or rfc)
    existentes = {t.rfc: t for t in listar(db, empresa_id=empresa_id)}
    creados = actualizados = 0
    for rfc, rs in roles.items():
        tipo = "ambos" if len(rs) == 2 else next(iter(rs))
        t = existentes.get(rfc)
        if t is None:
            db.add(Tercero(empresa_id=empresa_id, rfc=rfc, nombre=nombres[rfc][1][:255], tipo=tipo, origen="cfdi"))
            creados += 1
        else:
            nuevo_tipo = t.tipo
            if t.tipo != "ambos" and tipo != t.tipo:
                nuevo_tipo = "ambos"
            if nuevo_tipo != t.tipo:
                t.tipo = nuevo_tipo
                actualizados += 1
    db.commit()
    return creados, actualizados


# ---------- Cifras desde la bóveda ----------


def _stats_por_rfc(db: Session, *, empresa_id: uuid.UUID) -> dict[str, dict]:
    hace_12m = date.today() - timedelta(days=365)
    rfc_expr = case((Cfdi.direccion == "emitido", Cfdi.rfc_receptor), else_=Cfdi.rfc_emisor)
    filas = db.execute(
        select(
            rfc_expr.label("rfc"),
            func.count(),
            func.coalesce(func.sum(case((Cfdi.fecha >= hace_12m, Cfdi.total), else_=0)).filter(Cfdi.estatus == "vigente", Cfdi.tipo.in_(("ingreso", "egreso"))), 0),
            func.max(Cfdi.fecha),
            func.coalesce(func.sum(Cfdi.total).filter(Cfdi.estatus == "vigente", Cfdi.direccion == "emitido", Cfdi.tipo == "ingreso"), 0),
            func.coalesce(func.sum(Cfdi.total).filter(Cfdi.estatus == "vigente", Cfdi.direccion == "recibido", Cfdi.tipo == "egreso"), 0),
        )
        .where(Cfdi.empresa_id == empresa_id, Cfdi.tipo.in_(("ingreso", "egreso", "pago", "nota_credito")))
        .group_by("rfc")
    ).all()
    return {r: {"num": int(n), "f12": float(f12), "ult": ult, "emit": float(e), "rec": float(rc)} for r, n, f12, ult, e, rc in filas}


def _antiguedad(db: Session, *, empresa_id: uuid.UUID, rfc: str, tipo: str, pagado: dict) -> Antiguedad:
    """PPD vigentes menos lo pagado, agrupadas por días transcurridos."""
    col = Cfdi.rfc_receptor if tipo == "ingreso" else Cfdi.rfc_emisor
    filas = db.execute(
        select(Cfdi.uuid_fiscal, Cfdi.total, Cfdi.fecha).where(
            Cfdi.empresa_id == empresa_id, col == rfc, Cfdi.tipo == tipo, Cfdi.estatus == "vigente", Cfdi.metodo_pago_codigo == "PPD"
        )
    ).all()
    hoy = date.today()
    b = {"d0_30": Decimal("0"), "d31_60": Decimal("0"), "d61_90": Decimal("0"), "d90_mas": Decimal("0")}
    n = 0
    for u, total, fecha in filas:
        resto = Decimal(total) - pagado.get(u, (Decimal("0"), Decimal("0")))[0]
        if resto <= 0:
            continue
        n += 1
        d = (hoy - fecha).days
        k = "d0_30" if d <= 30 else "d31_60" if d <= 60 else "d61_90" if d <= 90 else "d90_mas"
        b[k] += resto
    total = sum(b.values(), Decimal("0"))
    return Antiguedad(d0_30=float(b["d0_30"]), d31_60=float(b["d31_60"]), d61_90=float(b["d61_90"]), d90_mas=float(b["d90_mas"]), total=float(total), num_cfdis=n)


def _saldos_por_rfc(db: Session, *, empresa_id: uuid.UUID) -> dict[str, float]:
    pagado = impuestos_crud.pagado_por_uuid(db, empresa_id=empresa_id)
    rfc_expr = case((Cfdi.direccion == "emitido", Cfdi.rfc_receptor), else_=Cfdi.rfc_emisor)
    filas = db.execute(
        select(rfc_expr, Cfdi.uuid_fiscal, Cfdi.total).where(
            Cfdi.empresa_id == empresa_id, Cfdi.estatus == "vigente", Cfdi.metodo_pago_codigo == "PPD", Cfdi.tipo.in_(("ingreso", "egreso"))
        )
    ).all()
    out: dict[str, Decimal] = {}
    for rfc, u, total in filas:
        resto = Decimal(total) - pagado.get(u, (Decimal("0"), Decimal("0")))[0]
        if resto > 0:
            out[rfc] = out.get(rfc, Decimal("0")) + resto
    return {k: float(v) for k, v in out.items()}


def a_resumen_lista(db: Session, *, empresa_id: uuid.UUID, terceros: list[Tercero]) -> list[TerceroResumenRead]:
    stats = _stats_por_rfc(db, empresa_id=empresa_id)
    saldos = _saldos_por_rfc(db, empresa_id=empresa_id)
    out = []
    for t in terceros:
        s = stats.get(t.rfc, {})
        out.append(
            TerceroResumenRead(
                **{k: getattr(t, k) for k in ("id", "rfc", "nombre", "tipo", "regimen_fiscal_codigo", "codigo_postal", "uso_cfdi_default", "email", "telefono", "contacto", "dias_credito", "notas", "origen", "activo", "created_at")},
                limite_credito=float(t.limite_credito) if t.limite_credito is not None else None,
                es_efos=t.rfc in RFCS_EFOS_MOCK,
                num_cfdis=s.get("num", 0),
                facturado_12m=s.get("f12", 0.0),
                saldo_pendiente=saldos.get(t.rfc, 0.0),
                ultimo_cfdi=s.get("ult"),
            )
        )
    return out


def a_detalle(db: Session, *, empresa_id: uuid.UUID, tercero: Tercero) -> TerceroDetalleRead:
    base = a_resumen_lista(db, empresa_id=empresa_id, terceros=[tercero])[0]
    pagado = impuestos_crud.pagado_por_uuid(db, empresa_id=empresa_id)
    stats = _stats_por_rfc(db, empresa_id=empresa_id).get(tercero.rfc, {})
    return TerceroDetalleRead(
        **base.model_dump(),
        por_cobrar=_antiguedad(db, empresa_id=empresa_id, rfc=tercero.rfc, tipo="ingreso", pagado=pagado),
        por_pagar=_antiguedad(db, empresa_id=empresa_id, rfc=tercero.rfc, tipo="egreso", pagado=pagado),
        total_emitido=stats.get("emit", 0.0),
        total_recibido=stats.get("rec", 0.0),
    )


# ---------- Carga masiva ----------

SINONIMOS = {
    "rfc": ["rfc"],
    "nombre": ["nombre", "razon social", "razón social", "cliente", "proveedor", "denominacion"],
    "tipo": ["tipo"],
    "email": ["email", "correo", "e-mail", "mail"],
    "telefono": ["telefono", "teléfono", "tel", "celular"],
    "contacto": ["contacto", "atencion", "persona"],
    "dias_credito": ["dias credito", "días crédito", "dias de credito", "credito dias", "plazo"],
    "limite_credito": ["limite credito", "límite crédito", "limite de credito"],
    "codigo_postal": ["codigo postal", "cp", "c.p."],
    "regimen": ["regimen", "régimen", "regimen fiscal"],
    "notas": ["notas", "observaciones", "comentarios"],
}
COLUMNAS_PLANTILLA = ["RFC", "Nombre / Razón social", "Tipo (cliente/proveedor/ambos)", "Email", "Teléfono", "Contacto", "Días crédito", "Límite crédito", "Código postal", "Régimen fiscal", "Notas"]


def importar_excel(db: Session, *, empresa_id: uuid.UUID, contenido: bytes, nombre: str) -> tuple[int, int, list[dict]]:
    tabla = [r for r in tabular.leer_tabla(contenido, nombre) if r and any(v not in (None, "") for v in r)]
    idx, mapa = tabular.localizar_encabezado(tabla, SINONIMOS, {"rfc", "nombre"})
    creados = actualizados = 0
    errores: list[dict] = []
    vistos: set[str] = set()
    for n, fila in enumerate(tabla[idx + 1 :], start=idx + 2):
        rfc = (tabular.texto(tabular.celda(fila, mapa, "rfc")) or "").upper()
        nombre_t = tabular.texto(tabular.celda(fila, mapa, "nombre"))
        if not rfc and not nombre_t:
            continue
        if len(rfc) not in (12, 13) or not nombre_t:
            errores.append({"fila": n, "rfc": rfc, "error": "RFC (12/13 caracteres) y nombre son obligatorios"})
            continue
        if rfc in vistos:
            errores.append({"fila": n, "rfc": rfc, "error": "RFC repetido en el archivo"})
            continue
        vistos.add(rfc)
        tipo = (tabular.texto(tabular.celda(fila, mapa, "tipo")) or "cliente").lower()
        if tipo not in ("cliente", "proveedor", "ambos"):
            errores.append({"fila": n, "rfc": rfc, "error": f"Tipo inválido '{tipo}'"})
            continue
        dias = tabular.a_decimal(tabular.celda(fila, mapa, "dias_credito"))
        limite = tabular.a_decimal(tabular.celda(fila, mapa, "limite_credito"))
        t = get_por_rfc(db, empresa_id=empresa_id, rfc=rfc)
        if t is None:
            t = Tercero(empresa_id=empresa_id, rfc=rfc, origen="excel")
            db.add(t)
            creados += 1
        else:
            actualizados += 1
        t.nombre = nombre_t[:255]
        t.tipo = tipo
        t.email = tabular.texto(tabular.celda(fila, mapa, "email"))
        t.telefono = tabular.texto(tabular.celda(fila, mapa, "telefono"))
        t.contacto = tabular.texto(tabular.celda(fila, mapa, "contacto"))
        t.dias_credito = int(dias) if dias is not None else 0
        t.limite_credito = limite
        cp = tabular.celda(fila, mapa, "codigo_postal")
        t.codigo_postal = (str(int(cp)) if isinstance(cp, float) else tabular.texto(cp)) or None
        t.regimen_fiscal_codigo = tabular.texto(tabular.celda(fila, mapa, "regimen"))
        t.notas = tabular.texto(tabular.celda(fila, mapa, "notas"))
    db.commit()
    return creados, actualizados, errores


def plantilla() -> bytes:
    return tabular.plantilla_xlsx(
        "Terceros", COLUMNAS_PLANTILLA,
        ["XAXX010101000", "Cliente Ejemplo SA de CV", "cliente", "pagos@cliente.com", "55 1234 5678", "Ana Pérez", 30, 250000, "06600", "601", ""],
        ["RFC y nombre son obligatorios; si el RFC ya existe se actualizan sus datos.", "Tipo: cliente, proveedor o ambos. Días crédito: plazo de pago acordado."],
    )
