import uuid
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import extract, func, select
from sqlalchemy.orm import Session

from app.modules.cfdi.models import Cfdi
from app.modules.conciliacion.importador import FilaBanco
from app.modules.conciliacion.models import CuentaBancaria, DeclaracionPeriodo, MovimientoBancario
from app.modules.conciliacion.schemas import (
    CandidatoCfdi,
    ColumnaBanco,
    ColumnaSat,
    DeclaracionRead,
    Diferencias,
    MovimientoBancoRead,
    ResumenConciliacion,
)
from app.modules.impuestos import crud as impuestos_crud
from app.modules.tenants.models import Empresa

TOLERANCIA_MONTO = Decimal("0.01")


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


def _cfdis_ya_conciliados(db: Session, *, empresa_id) -> set[uuid.UUID]:
    return set(
        db.scalars(
            select(MovimientoBancario.cfdi_id).where(MovimientoBancario.empresa_id == empresa_id, MovimientoBancario.cfdi_id.is_not(None))
        ).all()
    )


def candidatos_para(db: Session, *, mov: MovimientoBancario, tolerancia_dias: int = 5, limite: int = 10) -> list[CandidatoCfdi]:
    """CFDI vigentes que podrían corresponder al movimiento: misma dirección del
    dinero (abono ↔ emitidos cobrados; cargo ↔ recibidos pagados), monto igual
    (±0.01) y fecha cercana. Se excluyen los ya ligados a otro movimiento."""
    es_abono = Decimal(mov.abono or 0) > 0
    monto = Decimal(mov.abono if es_abono else mov.cargo)
    direccion = "emitido" if es_abono else "recibido"
    ocupados = _cfdis_ya_conciliados(db, empresa_id=mov.empresa_id) - ({mov.cfdi_id} if mov.cfdi_id else set())
    desde, hasta = mov.fecha - timedelta(days=tolerancia_dias), mov.fecha + timedelta(days=tolerancia_dias)
    stmt = (
        select(Cfdi)
        .where(
            Cfdi.empresa_id == mov.empresa_id,
            Cfdi.direccion == direccion,
            Cfdi.estatus == "vigente",
            Cfdi.tipo.in_(("ingreso", "egreso", "pago")),
            Cfdi.total.between(monto - TOLERANCIA_MONTO, monto + TOLERANCIA_MONTO),
            Cfdi.fecha.between(desde, hasta),
        )
        .order_by(Cfdi.fecha)
    )
    out = []
    for c in db.scalars(stmt):
        if c.id in ocupados:
            continue
        contraparte_nombre = c.nombre_receptor if direccion == "emitido" else c.nombre_emisor
        contraparte_rfc = c.rfc_receptor if direccion == "emitido" else c.rfc_emisor
        out.append(
            CandidatoCfdi(
                cfdi_id=c.id, uuid_fiscal=c.uuid_fiscal, tipo=c.tipo, direccion=c.direccion, fecha=c.fecha,
                nombre_contraparte=contraparte_nombre, rfc_contraparte=contraparte_rfc, total=float(c.total),
                diferencia=float(Decimal(c.total) - monto), dias=abs((c.fecha - mov.fecha).days),
            )
        )
    out.sort(key=lambda x: (x.dias, abs(x.diferencia)))
    return out[:limite]


def conciliar(db: Session, *, mov: MovimientoBancario, cfdi: Cfdi, por: str = "manual", nota: str | None = None) -> MovimientoBancario:
    mov.cfdi_id = cfdi.id
    mov.estado = "conciliado"
    mov.conciliado_por = por
    if nota is not None:
        mov.nota = nota
    db.commit()
    db.refresh(mov)
    return mov


def desconciliar(db: Session, *, mov: MovimientoBancario) -> MovimientoBancario:
    mov.cfdi_id = None
    mov.estado = "pendiente"
    mov.conciliado_por = None
    db.commit()
    db.refresh(mov)
    return mov


def ignorar(db: Session, *, mov: MovimientoBancario, nota: str | None) -> MovimientoBancario:
    mov.cfdi_id = None
    mov.estado = "ignorado"
    mov.conciliado_por = None
    mov.nota = nota
    db.commit()
    db.refresh(mov)
    return mov


def auto_conciliar(db: Session, *, empresa_id, cuenta_id=None, anio=None, mes=None, tolerancia_dias=5) -> tuple[int, int, int, int]:
    """Liga automáticamente los movimientos pendientes que tienen UN solo CFDI
    candidato. Si hay varios (ambiguo) o ninguno, se dejan pendientes."""
    pendientes, _ = listar_movimientos(db, empresa_id=empresa_id, cuenta_id=cuenta_id, anio=anio, mes=mes, estado="pendiente", limit=5000)
    conc = amb = sin = 0
    for mov in pendientes:
        cands = candidatos_para(db, mov=mov, tolerancia_dias=tolerancia_dias, limite=2)
        if len(cands) == 1:
            cfdi = db.get(Cfdi, cands[0].cfdi_id)
            conciliar(db, mov=mov, cfdi=cfdi, por="auto")
            conc += 1
        elif len(cands) > 1:
            amb += 1
        else:
            sin += 1
    return len(pendientes), conc, sin, amb


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
            func.coalesce(func.sum(base.c.abono).filter(base.c.estado == "conciliado"), 0),
            func.coalesce(func.sum(base.c.cargo).filter(base.c.estado == "conciliado"), 0),
            func.count().filter(base.c.estado == "pendiente"),
            func.count().filter(base.c.estado == "conciliado"),
            func.count().filter(base.c.estado == "ignorado"),
        )
    ).one()
    abonos, cargos, n, ab_c, ca_c, pend, conc, ign = fila
    relevantes = int(n) - int(ign)
    banco = ColumnaBanco(
        abonos=float(abonos), cargos=float(cargos), num_movimientos=int(n), abonos_conciliados=float(ab_c), cargos_conciliados=float(ca_c),
        pendientes=int(pend), conciliados=int(conc), ignorados=int(ign),
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


def a_movimiento_read(m: MovimientoBancario) -> MovimientoBancoRead:
    c = m.cfdi
    nombre = None
    if c is not None:
        nombre = c.nombre_receptor if c.direccion == "emitido" else c.nombre_emisor
    return MovimientoBancoRead(
        id=m.id, cuenta_id=m.cuenta_id, cuenta_alias=m.cuenta.alias, fecha=m.fecha, concepto=m.concepto, referencia=m.referencia,
        cargo=float(m.cargo), abono=float(m.abono), saldo=float(m.saldo) if m.saldo is not None else None, estado=m.estado,
        conciliado_por=m.conciliado_por, nota=m.nota, cfdi_id=m.cfdi_id, cfdi_uuid=c.uuid_fiscal if c else None,
        cfdi_nombre=nombre, cfdi_total=float(c.total) if c else None, archivo_nombre=m.archivo_nombre, created_at=m.created_at,
    )
