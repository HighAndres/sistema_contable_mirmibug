import re
import unicodedata
import uuid
from datetime import date, timedelta
from decimal import Decimal
from itertools import combinations

from sqlalchemy import extract, func, select
from sqlalchemy.orm import Session

from app.modules.cfdi import crud as cfdi_crud
from app.modules.cfdi.models import Cfdi
from app.modules.conciliacion.importador import FilaBanco
from app.modules.conciliacion.models import CuentaBancaria, DeclaracionPeriodo, LigaConciliacion, MovimientoBancario
from app.modules.conciliacion.schemas import (
    CandidatoCfdi,
    CandidatosResponse,
    ColumnaBanco,
    ColumnaSat,
    Combinacion,
    DeclaracionRead,
    Diferencias,
    LigaRead,
    MovimientoBancoRead,
    MovimientoResumen,
    ResumenConciliacion,
)
from app.modules.impuestos import crud as impuestos_crud
from app.modules.tenants.models import Empresa

TOLERANCIA_MONTO = Decimal("0.01")
# Ventana por defecto de la búsqueda asistida: una factura PPD se cobra a 30/60/90
# días, así que el pago suele caer en un mes distinto al de emisión.
DIAS_ATRAS_DEFAULT = 120
DIAS_ADELANTE_DEFAULT = 10
TOLERANCIA_PCT_DEFAULT = Decimal("2")
MAX_CFDI_COMBINACION = 4
MAX_COMBINACIONES = 6
TIPOS_CONCILIABLES = ("ingreso", "egreso", "pago")
_STOP = {"SA", "DE", "CV", "SC", "RL", "SAPI", "SAS", "SRL", "AC", "Y", "EL", "LA", "LOS", "LAS", "DEL"}


class ConciliacionError(ValueError):
    """Regla de negocio violada al ligar (importes, dirección, estatus)."""


# ---------- Cuentas ----------


def listar_cuentas(db: Session, *, empresa_id: uuid.UUID) -> list[CuentaBancaria]:
    return list(db.scalars(select(CuentaBancaria).where(CuentaBancaria.empresa_id == empresa_id).order_by(CuentaBancaria.alias)))


def get_cuenta(db: Session, *, empresa_id: uuid.UUID, cuenta_id: uuid.UUID) -> CuentaBancaria | None:
    return db.scalar(select(CuentaBancaria).where(CuentaBancaria.id == cuenta_id, CuentaBancaria.empresa_id == empresa_id))


def crear_cuenta(db: Session, *, empresa_id: uuid.UUID, **datos) -> CuentaBancaria:
    c = CuentaBancaria(empresa_id=empresa_id, **datos)
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


# ---------- Movimientos ----------


def importar_filas(
    db: Session, *, empresa_id: uuid.UUID, cuenta: CuentaBancaria, filas: list[FilaBanco], archivo_nombre: str | None
) -> tuple[int, int]:
    huellas_existentes = set(
        db.scalars(select(MovimientoBancario.huella).where(MovimientoBancario.cuenta_id == cuenta.id)).all()
    )
    nuevos, dup = 0, 0
    for f in filas:
        if f.huella in huellas_existentes:
            dup += 1
            continue
        db.add(
            MovimientoBancario(
                empresa_id=empresa_id,
                cuenta_id=cuenta.id,
                fecha=f.fecha,
                concepto=f.concepto,
                referencia=f.referencia,
                cargo=f.cargo,
                abono=f.abono,
                saldo=f.saldo,
                huella=f.huella,
                fila_origen=f.fila,
                archivo_nombre=archivo_nombre,
            )
        )
        huellas_existentes.add(f.huella)
        nuevos += 1
    db.commit()
    return nuevos, dup


def _filtro_movs(stmt, *, empresa_id, cuenta_id=None, anio=None, mes=None, estado=None):
    stmt = stmt.where(MovimientoBancario.empresa_id == empresa_id)
    if cuenta_id:
        stmt = stmt.where(MovimientoBancario.cuenta_id == cuenta_id)
    if anio:
        stmt = stmt.where(extract("year", MovimientoBancario.fecha) == anio)
    if mes:
        stmt = stmt.where(extract("month", MovimientoBancario.fecha) == mes)
    if estado:
        stmt = stmt.where(MovimientoBancario.estado == estado)
    return stmt


def listar_movimientos(db: Session, *, empresa_id, cuenta_id=None, anio=None, mes=None, estado=None, q=None, limit=200, offset=0) -> tuple[list[MovimientoBancario], int]:
    stmt = _filtro_movs(select(MovimientoBancario), empresa_id=empresa_id, cuenta_id=cuenta_id, anio=anio, mes=mes, estado=estado)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(MovimientoBancario.concepto.ilike(like) | MovimientoBancario.referencia.ilike(like))
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    items = list(db.scalars(stmt.order_by(MovimientoBancario.fecha.desc(), MovimientoBancario.created_at.desc()).limit(limit).offset(offset)))
    return items, total


def get_movimiento(db: Session, *, empresa_id, movimiento_id) -> MovimientoBancario | None:
    return db.scalar(select(MovimientoBancario).where(MovimientoBancario.id == movimiento_id, MovimientoBancario.empresa_id == empresa_id))


def _normalizar(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Z0-9 ]+", " ", t.upper())


def _contraparte_en_concepto(concepto: str, nombre: str, rfc: str) -> bool:
    """El banco suele traer el nombre o RFC del ordenante en el concepto del SPEI."""
    c = _normalizar(concepto)
    if rfc and rfc.upper() in c:
        return True
    tokens = [t for t in _normalizar(nombre).split() if len(t) >= 4 and t not in _STOP]
    if not tokens:
        return False
    hits = sum(1 for t in tokens if t in c)
    return hits >= 2 or (hits == 1 and len(tokens) == 1)


def _direccion_de(mov: MovimientoBancario) -> str:
    return "emitido" if Decimal(mov.abono or 0) > 0 else "recibido"


def _contraparte(c: Cfdi) -> tuple[str, str]:
    return (c.nombre_receptor, c.rfc_receptor) if c.direccion == "emitido" else (c.nombre_emisor, c.rfc_emisor)


def _serie_folio(c: Cfdi) -> str | None:
    if not (c.serie or c.folio):
        return None
    return f"{c.serie or ''}{'-' if c.serie and c.folio else ''}{c.folio or ''}"


def ligado_por_cfdi(db: Session, *, empresa_id, cfdi_ids: list[uuid.UUID], excluir_mov: uuid.UUID | None = None) -> dict[uuid.UUID, Decimal]:
    """{cfdi_id: importe ya aplicado desde movimientos bancarios} (N:1)."""
    if not cfdi_ids:
        return {}
    stmt = (
        select(LigaConciliacion.cfdi_id, func.coalesce(func.sum(LigaConciliacion.importe), 0))
        .join(MovimientoBancario, MovimientoBancario.id == LigaConciliacion.movimiento_id)
        .where(MovimientoBancario.empresa_id == empresa_id, LigaConciliacion.cfdi_id.in_(cfdi_ids))
        .group_by(LigaConciliacion.cfdi_id)
    )
    if excluir_mov is not None:
        stmt = stmt.where(LigaConciliacion.movimiento_id != excluir_mov)
    return {cid: Decimal(v) for cid, v in db.execute(stmt).all()}


def _saldos_cfdi(db: Session, *, empresa_id, cfdis: list[Cfdi], excluir_mov=None) -> dict[uuid.UUID, tuple[Decimal, Decimal, Decimal]]:
    """{cfdi_id: (pagado por REP, ligado desde otros movimientos, saldo ligable)}."""
    ligado = ligado_por_cfdi(db, empresa_id=empresa_id, cfdi_ids=[c.id for c in cfdis], excluir_mov=excluir_mov)
    uuids_ppd = [c.uuid_fiscal for c in cfdis if c.tipo in ("ingreso", "egreso") and c.metodo_pago_codigo == "PPD"]
    rep = cfdi_crud.pagado_rep_de(db, empresa_id=empresa_id, uuids=uuids_ppd)
    out = {}
    for c in cfdis:
        pagado_rep = rep.get(c.uuid_fiscal, Decimal("0"))
        lig = ligado.get(c.id, Decimal("0"))
        out[c.id] = (pagado_rep, lig, Decimal(c.total) - pagado_rep - lig)
    return out


def _tolerancia(restante: Decimal, tolerancia_pct: Decimal) -> Decimal:
    return max(Decimal("1.00"), (restante * tolerancia_pct / 100).quantize(Decimal("0.01")))


def _clasificar(saldo: Decimal, restante: Decimal, tol: Decimal) -> str:
    dif = saldo - restante
    if abs(dif) <= TOLERANCIA_MONTO:
        return "exacto"
    if abs(dif) <= tol:
        return "similar"
    return "parcial" if dif > 0 else "menor"


_RANK = {"exacto": 0, "similar": 1, "parcial": 2, "menor": 3}


def candidatos_para(
    db: Session,
    *,
    mov: MovimientoBancario,
    dias_atras: int = DIAS_ATRAS_DEFAULT,
    dias_adelante: int = DIAS_ADELANTE_DEFAULT,
    tolerancia_pct: Decimal = TOLERANCIA_PCT_DEFAULT,
    q: str | None = None,
    solo_exactos: bool = False,
    limite: int = 30,
) -> CandidatosResponse:
    """Búsqueda asistida: CFDI vigentes en la misma dirección del dinero (abono ↔
    emitidos; cargo ↔ recibidos) con saldo por ligar, dentro de la ventana de
    fechas. Cada candidato trae cómo coincide (exacto / similar / parcial /
    menor) y se sugieren combinaciones de varios CFDI de la misma contraparte
    que sumen lo que falta del movimiento. Con `q` se busca por contraparte,
    RFC, folio o UUID sin importar el monto."""
    restante = mov.restante
    resumen = MovimientoResumen(id=mov.id, fecha=mov.fecha, monto=float(mov.monto), importe_ligado=float(mov.importe_ligado), restante=float(restante))
    if restante <= TOLERANCIA_MONTO:
        return CandidatosResponse(movimiento=resumen, candidatos=[], combinaciones=[])
    direccion = _direccion_de(mov)
    desde, hasta = mov.fecha - timedelta(days=dias_atras), mov.fecha + timedelta(days=dias_adelante)
    stmt = select(Cfdi).where(
        Cfdi.empresa_id == mov.empresa_id,
        Cfdi.direccion == direccion,
        Cfdi.estatus == "vigente",
        Cfdi.tipo.in_(TIPOS_CONCILIABLES),
        Cfdi.total > 0,
    )
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            Cfdi.nombre_emisor.ilike(like) | Cfdi.nombre_receptor.ilike(like) | Cfdi.rfc_emisor.ilike(like)
            | Cfdi.rfc_receptor.ilike(like) | Cfdi.folio.ilike(like) | Cfdi.uuid_fiscal.ilike(like)
        )
    else:
        stmt = stmt.where(Cfdi.fecha.between(desde, hasta))
    if solo_exactos:
        stmt = stmt.where(Cfdi.total >= restante - TOLERANCIA_MONTO)
    cfdis = list(db.scalars(stmt.order_by(Cfdi.fecha.desc()).limit(400)))
    saldos = _saldos_cfdi(db, empresa_id=mov.empresa_id, cfdis=cfdis, excluir_mov=mov.id)
    tol = _tolerancia(restante, tolerancia_pct)

    ya_ligados = {l.cfdi_id for l in mov.ligas}
    out: list[CandidatoCfdi] = []
    for c in cfdis:
        if c.id in ya_ligados:
            continue  # ya aplicado a este movimiento: se edita desde sus ligas, no como candidato
        pagado_rep, lig, saldo = saldos[c.id]
        if saldo <= TOLERANCIA_MONTO:
            continue  # ya cobrado/pagado por completo
        coincidencia = _clasificar(saldo, restante, tol)
        if solo_exactos and coincidencia != "exacto":
            continue
        nombre, rfc = _contraparte(c)
        out.append(
            CandidatoCfdi(
                cfdi_id=c.id, uuid_fiscal=c.uuid_fiscal, tipo=c.tipo, direccion=c.direccion, metodo_pago=c.metodo_pago_codigo,
                serie_folio=_serie_folio(c), fecha=c.fecha, nombre_contraparte=nombre, rfc_contraparte=rfc, total=float(c.total),
                pagado_rep=float(pagado_rep), ligado_otros=float(lig), saldo=float(saldo), diferencia=float(saldo - restante),
                dias=abs((mov.fecha - c.fecha).days), pagado_despues=mov.fecha >= c.fecha, coincidencia=coincidencia,
                contraparte_en_concepto=_contraparte_en_concepto(mov.concepto, nombre, rfc),
                importe_sugerido=float(min(saldo, restante)),
            )
        )
    # Exactos y similares primero; entre parciales y menores manda que la contraparte
    # aparezca en el concepto del banco (es la pista más fuerte), luego la cercanía.
    out.sort(key=lambda x: (min(_RANK[x.coincidencia], 2), not x.contraparte_en_concepto, _RANK[x.coincidencia], x.dias, abs(x.diferencia)))
    combos = [] if solo_exactos else _combinaciones(out, restante=restante, tol=tol)
    return CandidatosResponse(movimiento=resumen, candidatos=out[:limite], combinaciones=combos)


def _combinaciones(cands: list[CandidatoCfdi], *, restante: Decimal, tol: Decimal) -> list[Combinacion]:
    """Subconjuntos (2..4) de CFDI 'menores' de la misma contraparte cuya suma
    cae en restante ± tolerancia. Un solo pago que liquida varias facturas."""
    por_rfc: dict[str, list[CandidatoCfdi]] = {}
    for c in cands:
        if c.coincidencia == "menor":
            por_rfc.setdefault(c.rfc_contraparte, []).append(c)
    combos: list[Combinacion] = []
    for rfc, grupo in por_rfc.items():
        grupo = sorted(grupo, key=lambda x: x.dias)[:12]  # acota el espacio de búsqueda
        saldos = [Decimal(str(g.saldo)) for g in grupo]
        for n in range(2, min(MAX_CFDI_COMBINACION, len(grupo)) + 1):
            for idx in combinations(range(len(grupo)), n):
                total = sum((saldos[i] for i in idx), Decimal("0"))
                if abs(total - restante) <= tol:
                    combos.append(
                        Combinacion(
                            cfdi_ids=[grupo[i].cfdi_id for i in idx], rfc_contraparte=rfc, nombre_contraparte=grupo[0].nombre_contraparte,
                            total=float(total), diferencia=float(total - restante),
                        )
                    )
                if len(combos) >= MAX_COMBINACIONES * 3:
                    break
    combos.sort(key=lambda x: (abs(x.diferencia), len(x.cfdi_ids)))
    return combos[:MAX_COMBINACIONES]


def _actualizar_estado(mov: MovimientoBancario, *, por: str | None) -> None:
    ligado = mov.importe_ligado
    if ligado <= 0:
        mov.estado, mov.conciliado_por = "pendiente", None
    elif ligado >= mov.monto - TOLERANCIA_MONTO:
        mov.estado, mov.conciliado_por = "conciliado", por or mov.conciliado_por or "manual"
    else:
        mov.estado, mov.conciliado_por = "parcial", por or mov.conciliado_por or "manual"


def conciliar(
    db: Session, *, mov: MovimientoBancario, ligas: list[tuple[Cfdi, Decimal | None]], por: str = "manual", nota: str | None = None
) -> MovimientoBancario:
    """Aplica uno o varios CFDI al movimiento. Sin importe se aplica lo que quepa.
    Valida dirección, estatus y que no se rebase ni el saldo del CFDI ni el
    monto del movimiento (con tolerancia de centavos)."""
    if mov.estado == "ignorado":
        raise ConciliacionError("El movimiento está marcado como ignorado; vuélvelo a pendiente primero")
    direccion = _direccion_de(mov)
    cfdis = [c for c, _ in ligas]
    saldos = _saldos_cfdi(db, empresa_id=mov.empresa_id, cfdis=cfdis, excluir_mov=mov.id)
    existentes = {l.cfdi_id: l for l in mov.ligas}
    restante = mov.restante
    for c, importe in ligas:
        if c.empresa_id != mov.empresa_id:
            raise ConciliacionError("CFDI de otra empresa")
        if c.estatus != "vigente":
            raise ConciliacionError(f"El CFDI {c.uuid_fiscal} no está vigente")
        if c.tipo not in TIPOS_CONCILIABLES:
            raise ConciliacionError(f"El CFDI {c.uuid_fiscal} es de tipo {c.tipo}; solo se concilian ingresos, gastos y complementos de pago")
        if c.direccion != direccion:
            raise ConciliacionError("Un abono solo se liga con CFDI emitidos y un cargo con CFDI recibidos")
        _, _, saldo = saldos[c.id]
        if c.id in existentes:  # re-ligar el mismo CFDI: se reemplaza el importe anterior
            saldo += Decimal(existentes[c.id].importe)
            restante += Decimal(existentes[c.id].importe)
        if saldo <= TOLERANCIA_MONTO:
            raise ConciliacionError(f"El CFDI {c.uuid_fiscal} ya está cubierto por completo (REP u otros movimientos)")
        aplicar = importe if importe is not None else min(saldo, restante)
        aplicar = Decimal(aplicar).quantize(Decimal("0.01"))
        if aplicar <= 0:
            raise ConciliacionError("El importe a ligar debe ser mayor a cero")
        if aplicar > saldo + TOLERANCIA_MONTO:
            raise ConciliacionError(f"El importe {aplicar} supera el saldo por ligar del CFDI ({saldo})")
        if aplicar > restante + TOLERANCIA_MONTO:
            raise ConciliacionError(f"El importe {aplicar} supera lo que le falta al movimiento ({restante})")
        if c.id in existentes:
            existentes[c.id].importe = aplicar
        else:
            mov.ligas.append(LigaConciliacion(cfdi_id=c.id, importe=aplicar))
        restante -= aplicar
    _actualizar_estado(mov, por=por)
    if nota is not None:
        mov.nota = nota
    db.commit()
    db.refresh(mov)
    return mov


def quitar_liga(db: Session, *, mov: MovimientoBancario, cfdi_id: uuid.UUID) -> MovimientoBancario:
    liga = next((l for l in mov.ligas if l.cfdi_id == cfdi_id), None)
    if liga is None:
        raise ConciliacionError("Ese CFDI no está ligado al movimiento")
    mov.ligas.remove(liga)
    _actualizar_estado(mov, por=None)
    db.commit()
    db.refresh(mov)
    return mov


def desconciliar(db: Session, *, mov: MovimientoBancario) -> MovimientoBancario:
    mov.ligas.clear()
    mov.estado = "pendiente"
    mov.conciliado_por = None
    db.commit()
    db.refresh(mov)
    return mov


def ignorar(db: Session, *, mov: MovimientoBancario, nota: str | None) -> MovimientoBancario:
    mov.ligas.clear()
    mov.estado = "ignorado"
    mov.conciliado_por = None
    mov.nota = nota
    db.commit()
    db.refresh(mov)
    return mov


def auto_conciliar(db: Session, *, empresa_id, cuenta_id=None, anio=None, mes=None, tolerancia_dias=5) -> tuple[int, int, int, int, int]:
    """Liga sola solo lo seguro: movimientos pendientes con UN único CFDI de
    monto exacto a ±tolerancia_dias. Lo demás queda para la revisión asistida:
    `ambiguos` (varios exactos) y `con_sugerencias` (similares, parciales o
    combinaciones en la ventana amplia)."""
    pendientes, _ = listar_movimientos(db, empresa_id=empresa_id, cuenta_id=cuenta_id, anio=anio, mes=mes, estado="pendiente", limit=5000)
    conc = amb = sin = sug = 0
    for mov in pendientes:
        exactos = candidatos_para(db, mov=mov, dias_atras=tolerancia_dias, dias_adelante=tolerancia_dias, solo_exactos=True, limite=2).candidatos
        if len(exactos) == 1:
            cfdi = db.get(Cfdi, exactos[0].cfdi_id)
            conciliar(db, mov=mov, ligas=[(cfdi, None)], por="auto")
            conc += 1
        elif len(exactos) > 1:
            amb += 1
        else:
            amplio = candidatos_para(db, mov=mov)
            if amplio.candidatos or amplio.combinaciones:
                sug += 1
            else:
                sin += 1
    return len(pendientes), conc, sin, amb, sug


# ---------- Declaraciones ----------


def get_declaracion(db: Session, *, empresa_id, anio, mes) -> DeclaracionPeriodo | None:
    return db.scalar(select(DeclaracionPeriodo).where(DeclaracionPeriodo.empresa_id == empresa_id, DeclaracionPeriodo.anio == anio, DeclaracionPeriodo.mes == mes))


def upsert_declaracion(db: Session, *, empresa_id, anio, mes, datos: dict) -> DeclaracionPeriodo:
    d = get_declaracion(db, empresa_id=empresa_id, anio=anio, mes=mes)
    if d is None:
        d = DeclaracionPeriodo(empresa_id=empresa_id, anio=anio, mes=mes)
        db.add(d)
    for k, v in datos.items():
        setattr(d, k, v)
    db.commit()
    db.refresh(d)
    return d


def a_declaracion_read(d: DeclaracionPeriodo | None, *, anio: int, mes: int) -> DeclaracionRead:
    if d is None:
        return DeclaracionRead(anio=anio, mes=mes, ingresos_declarados=None, deducciones_declaradas=None, iva_declarado=None, isr_declarado=None, fecha_presentacion=None, numero_operacion=None, notas=None, capturada=False)
    f = lambda v: float(v) if v is not None else None  # noqa: E731
    return DeclaracionRead(
        anio=d.anio, mes=d.mes, ingresos_declarados=f(d.ingresos_declarados), deducciones_declaradas=f(d.deducciones_declaradas),
        iva_declarado=f(d.iva_declarado), isr_declarado=f(d.isr_declarado), fecha_presentacion=d.fecha_presentacion,
        numero_operacion=d.numero_operacion, notas=d.notas, capturada=True,
    )


# ---------- Resumen a tres columnas ----------


def resumen(db: Session, *, empresa: Empresa, anio: int, mes: int) -> ResumenConciliacion:
    empresa_id = empresa.id
    # SAT (bóveda)
    iva = impuestos_crud.iva_periodo(db, empresa_id=empresa_id, anio=anio, mes=mes)
    isr = impuestos_crud.isr_ejercicio(db, empresa=empresa, anio=anio, hasta_mes=mes)
    isr_mes = float(isr.meses[-1].isr_del_mes) if isr.meses else 0.0
    ing_cobrados = sum((f.base for f in iva.emitidas if f.concepto in ("PUE", "REP")), Decimal("0"))
    egr_pagados = sum((f.base for f in iva.recibidas if f.concepto in ("PUE", "REP")), Decimal("0"))
    ing_facturados = sum((f.base for f in iva.emitidas if f.concepto in ("PUE", "REP", "PPD pendiente")), Decimal("0"))
    num_cfdis = db.scalar(
        select(func.count()).where(Cfdi.empresa_id == empresa_id, extract("year", Cfdi.fecha) == anio, extract("month", Cfdi.fecha) == mes)
    ) or 0
    sat = ColumnaSat(
        ingresos_cobrados=float(ing_cobrados), egresos_pagados=float(egr_pagados), ingresos_facturados=float(ing_facturados),
        iva_saldo=float(iva.saldo), isr_estimado=isr_mes, num_cfdis=int(num_cfdis),
    )

    # Banco
    base = _filtro_movs(select(MovimientoBancario), empresa_id=empresa_id, anio=anio, mes=mes).subquery()
    fila = db.execute(
        select(
            func.coalesce(func.sum(base.c.abono), 0),
            func.coalesce(func.sum(base.c.cargo), 0),
            func.count(),
            func.count().filter(base.c.estado == "pendiente"),
            func.count().filter(base.c.estado == "parcial"),
            func.count().filter(base.c.estado == "conciliado"),
            func.count().filter(base.c.estado == "ignorado"),
        )
    ).one()
    abonos, cargos, n, pend, parc, conc, ign = fila
    # Lo conciliado se mide por importe ligado (cuenta también lo parcial).
    ab_c, ca_c = db.execute(
        select(
            func.coalesce(func.sum(LigaConciliacion.importe).filter(base.c.abono > 0), 0),
            func.coalesce(func.sum(LigaConciliacion.importe).filter(base.c.cargo > 0), 0),
        ).select_from(LigaConciliacion).join(base, base.c.id == LigaConciliacion.movimiento_id)
    ).one()
    relevantes = int(n) - int(ign)
    banco = ColumnaBanco(
        abonos=float(abonos), cargos=float(cargos), num_movimientos=int(n), abonos_conciliados=float(ab_c), cargos_conciliados=float(ca_c),
        pendientes=int(pend), parciales=int(parc), conciliados=int(conc), ignorados=int(ign),
        porcentaje_conciliado=round(100 * int(conc) / relevantes, 1) if relevantes else 0.0,
    )

    # Declarado
    decl = get_declaracion(db, empresa_id=empresa_id, anio=anio, mes=mes)
    declarado = a_declaracion_read(decl, anio=anio, mes=mes)

    # Los abonos del banco traen IVA; los ingresos cobrados del SAT son base sin IVA.
    # Se compara contra el total con IVA de lo cobrado (base × 1.16 aprox.) usando el
    # IVA real de la bóveda: base + IVA trasladado cobrado.
    ingresos_sat_con_iva = float(ing_cobrados + iva.trasladado_cobrado)
    dif = Diferencias(
        ingresos_sat_vs_banco=round(ingresos_sat_con_iva - float(abonos), 2),
        ingresos_sat_vs_declarado=round(float(ing_cobrados) - declarado.ingresos_declarados, 2) if declarado.ingresos_declarados is not None else None,
        iva_sat_vs_declarado=round(float(iva.saldo) - declarado.iva_declarado, 2) if declarado.iva_declarado is not None else None,
        isr_sat_vs_declarado=round(isr_mes - declarado.isr_declarado, 2) if declarado.isr_declarado is not None else None,
    )
    if not declarado.capturada:
        semaforo = "sin_declaracion"
    else:
        semaforo = "ok" if all(abs(v or 0) < 1 for v in (dif.ingresos_sat_vs_declarado, dif.iva_sat_vs_declarado, dif.isr_sat_vs_declarado)) else "revisar"
    return ResumenConciliacion(anio=anio, mes=mes, sat=sat, banco=banco, declarado=declarado, diferencias=dif, semaforo=semaforo)


def a_liga_read(l: LigaConciliacion) -> LigaRead:
    c = l.cfdi
    nombre, rfc = _contraparte(c)
    return LigaRead(
        cfdi_id=c.id, uuid_fiscal=c.uuid_fiscal, tipo=c.tipo, serie_folio=_serie_folio(c), fecha=c.fecha,
        nombre_contraparte=nombre, rfc_contraparte=rfc, total=float(c.total), importe=float(l.importe),
    )


def a_movimiento_read(m: MovimientoBancario) -> MovimientoBancoRead:
    ligas = [a_liga_read(l) for l in m.ligas]
    if not ligas:
        cfdi_uuid = cfdi_nombre = None
    elif len(ligas) == 1:
        cfdi_uuid, cfdi_nombre = ligas[0].uuid_fiscal, ligas[0].nombre_contraparte
    else:
        nombres = {l.nombre_contraparte for l in ligas}
        cfdi_uuid = None
        cfdi_nombre = f"{len(ligas)} CFDI · {next(iter(nombres))}" if len(nombres) == 1 else f"{len(ligas)} CFDI · {len(nombres)} contrapartes"
    return MovimientoBancoRead(
        id=m.id, cuenta_id=m.cuenta_id, cuenta_alias=m.cuenta.alias, fecha=m.fecha, concepto=m.concepto, referencia=m.referencia,
        cargo=float(m.cargo), abono=float(m.abono), saldo=float(m.saldo) if m.saldo is not None else None, estado=m.estado,
        conciliado_por=m.conciliado_por, nota=m.nota, ligas=ligas, importe_ligado=float(m.importe_ligado), restante=float(m.restante),
        cfdi_uuid=cfdi_uuid, cfdi_nombre=cfdi_nombre, archivo_nombre=m.archivo_nombre, created_at=m.created_at,
    )
