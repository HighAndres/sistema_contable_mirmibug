import uuid
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import EmpresaContext, require_permissions
from app.db.session import get_db
from app.modules.bitacora import crud as bitacora_crud
from app.modules.cfdi import crud
from app.modules.cfdi.models import Cfdi
from app.modules.cfdi.schemas import (
    CfdiConceptoRead,
    CfdiDetalleRead,
    CfdiPage,
    CfdiRead,
    CfdiResumen,
    PagoDoctoRead,
    PagoManualRequest,
)
from app.modules.rules import crud as rules_crud

router = APIRouter(prefix="/cfdi", tags=["cfdi"])


def _filtros(
    tipo: str | None = Query(default=None, pattern="^(ingreso|egreso|pago|nomina|nota_credito)$"),
    direccion: str | None = Query(default=None, pattern="^(emitido|recibido)$"),
    estatus: str | None = Query(default=None, pattern="^(vigente|cancelado|en_proceso)$"),
    emisor: str | None = Query(default=None, description="RFC o nombre (contiene)"),
    receptor: str | None = Query(default=None, description="RFC o nombre (contiene)"),
    anio: int | None = Query(default=None, ge=2000, le=2100),
    mes: int | None = Query(default=None, ge=1, le=12),
    fecha_desde: date | None = None,
    fecha_hasta: date | None = None,
    metodo_pago: str | None = Query(default=None, pattern="^(PUE|PPD)$"),
    forma_pago: str | None = Query(default=None, max_length=5),
    uuid_fiscal: str | None = Query(default=None, max_length=36),
    q: str | None = Query(default=None, max_length=120, description="Búsqueda libre: UUID, folio, RFC, nombre"),
    estado_pago: str | None = Query(default=None, pattern="^(pagada|pendiente)$", description="Solo facturas: pagada (PUE, PPD con REP completo o marcada a mano) o pendiente (PPD sin pagar)"),
) -> dict:
    return {
        "tipo": tipo,
        "direccion": direccion,
        "estatus": estatus,
        "emisor": emisor,
        "receptor": receptor,
        "anio": anio,
        "mes": mes,
        "fecha_desde": fecha_desde,
        "fecha_hasta": fecha_hasta,
        "metodo_pago": metodo_pago,
        "forma_pago": forma_pago,
        "uuid_fiscal": uuid_fiscal,
        "q": q,
        "estado_pago": estado_pago,
    }


def _con_estado_pago(db: Session, *, empresa_id: uuid.UUID, cfdis: list[Cfdi]) -> list[CfdiRead]:
    """Convierte a CfdiRead agregando lo pagado por REP y el estado de pago."""
    pagado = crud.pagado_rep_de(db, empresa_id=empresa_id, uuids=[c.uuid_fiscal for c in cfdis if c.metodo_pago_codigo == "PPD"])
    out = []
    for c in cfdis:
        p = pagado.get(c.uuid_fiscal, Decimal("0"))
        base = CfdiRead.model_validate(c, from_attributes=True)
        out.append(base.model_copy(update={"estado_pago": crud.estado_pago_de(c, p), "pagado_rep": float(p)}))
    return out


def _factura(db: Session, *, ctx: EmpresaContext, cfdi_id: uuid.UUID) -> Cfdi:
    cfdi = crud.get(db, empresa_id=ctx.empresa.id, cfdi_id=cfdi_id)
    if cfdi is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "CFDI no encontrado")
    return cfdi


@router.get("", response_model=CfdiPage)
def listar(
    filtros: dict = Depends(_filtros),
    orden: str = Query(default="fecha_desc", pattern="^(fecha_desc|fecha_asc|total_desc|total_asc)$"),
    limit: int = Query(50, le=500),
    offset: int = 0,
    ctx: EmpresaContext = Depends(require_permissions("cfdi.leer")),
    db: Session = Depends(get_db),
) -> CfdiPage:
    items, total = crud.list_paginado(db, empresa_id=ctx.empresa.id, limit=limit, offset=offset, orden=orden, **filtros)
    return CfdiPage(items=_con_estado_pago(db, empresa_id=ctx.empresa.id, cfdis=items), total=total, limit=limit, offset=offset)


@router.get("/resumen", response_model=CfdiResumen)
def resumen(
    filtros: dict = Depends(_filtros),
    ctx: EmpresaContext = Depends(require_permissions("cfdi.leer")),
    db: Session = Depends(get_db),
) -> CfdiResumen:
    """Tarjetas por tipo (ingresos, gastos, pagos, nómina) para los mismos filtros
    de la lista, ignorando el filtro `tipo` para que las 4 tarjetas siempre se vean."""
    por_tipo = crud.resumen_por_tipo(db, empresa_id=ctx.empresa.id, **filtros)
    return CfdiResumen(**por_tipo, anios=crud.anios_disponibles(db, empresa_id=ctx.empresa.id))


@router.get("/{cfdi_id}", response_model=CfdiDetalleRead)
def detalle(
    cfdi_id: uuid.UUID,
    ctx: EmpresaContext = Depends(require_permissions("cfdi.leer")),
    db: Session = Depends(get_db),
) -> CfdiDetalleRead:
    cfdi = crud.get(db, empresa_id=ctx.empresa.id, cfdi_id=cfdi_id)
    if cfdi is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "CFDI no encontrado")
    from app.modules.sat import carga_xml

    alertas = rules_crud.list_alertas_de_cfdi(db, cfdi_id=cfdi.id)
    pagos_recibidos = []
    if cfdi.metodo_pago_codigo == "PPD":
        pagos_recibidos = [
            PagoDoctoRead(
                cfdi_pago_id=p.cfdi_pago_id, uuid_pago=p.cfdi_pago.uuid_fiscal, uuid_relacionado=p.uuid_relacionado,
                num_parcialidad=p.num_parcialidad, imp_saldo_anterior=p.imp_saldo_anterior, imp_pagado=p.imp_pagado,
                imp_saldo_insoluto=p.imp_saldo_insoluto, iva_pagado=p.iva_pagado, fecha_pago=p.fecha_pago, forma_pago_codigo=p.forma_pago_codigo,
            )
            for p in carga_xml.pagos_de_factura(db, empresa_id=ctx.empresa.id, uuid_fiscal=cfdi.uuid_fiscal)
        ]
    pagos_relacionados = [
        PagoDoctoRead(
            cfdi_pago_id=p.cfdi_pago_id, uuid_pago=cfdi.uuid_fiscal, uuid_relacionado=p.uuid_relacionado,
            num_parcialidad=p.num_parcialidad, imp_saldo_anterior=p.imp_saldo_anterior, imp_pagado=p.imp_pagado,
            imp_saldo_insoluto=p.imp_saldo_insoluto, iva_pagado=p.iva_pagado, fecha_pago=p.fecha_pago, forma_pago_codigo=p.forma_pago_codigo,
        )
        for p in cfdi.pagos_relacionados
    ]
    saldo = None
    if cfdi.metodo_pago_codigo == "PPD":
        # Marcada a mano = saldada, aunque no haya REP que la cubra.
        saldo = 0.0 if cfdi.pagada_manualmente else float(cfdi.total) - float(sum((p.imp_pagado for p in pagos_recibidos), 0))
    base = _con_estado_pago(db, empresa_id=ctx.empresa.id, cfdis=[cfdi])[0]
    return CfdiDetalleRead(
        **base.model_dump(),
        conceptos=[CfdiConceptoRead.model_validate(c, from_attributes=True) for c in cfdi.conceptos],
        alertas=alertas,
        pagos_recibidos=pagos_recibidos,
        pagos_relacionados=pagos_relacionados,
        saldo_pendiente=saldo,
        tiene_xml=bool(cfdi.xml),
    )


@router.post("/{cfdi_id}/pago-manual", response_model=CfdiRead)
def marcar_pago_manual(
    cfdi_id: uuid.UUID,
    payload: PagoManualRequest,
    ctx: EmpresaContext = Depends(require_permissions("cfdi.editar")),
    db: Session = Depends(get_db),
) -> CfdiRead:
    """Marca una factura PPD como pagada/cobrada a mano (sin REP ni movimiento
    bancario). Desde ese momento cuenta como cobrada/pagada en la fecha dada
    para IVA base flujo, ISR en flujo, saldos de clientes/proveedores y reportes."""
    cfdi = _factura(db, ctx=ctx, cfdi_id=cfdi_id)
    pagado = crud.pagado_rep_de(db, empresa_id=ctx.empresa.id, uuids=[cfdi.uuid_fiscal]).get(cfdi.uuid_fiscal, Decimal("0"))
    try:
        crud.marcar_pago_manual(db, cfdi=cfdi, fecha=payload.fecha, nota=payload.nota, usuario_id=ctx.usuario.id, pagado_rep=pagado)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    verbo = "cobrada" if cfdi.direccion == "emitido" else "pagada"
    folio = "-".join(filter(None, (cfdi.serie, cfdi.folio))) or f"{cfdi.uuid_fiscal[:8]}…"
    bitacora_crud.registrar(
        db,
        empresa_id=ctx.empresa.id,
        usuario=ctx.usuario,
        accion="cfdi.pago_manual",
        descripcion=f"Factura {folio} marcada como {verbo} a mano el {payload.fecha.isoformat()}"
        + (f": {cfdi.pago_manual_nota}" if cfdi.pago_manual_nota else ""),
        entidad_tipo="cfdi",
        entidad_id=cfdi.id,
        metadatos={"fecha": payload.fecha.isoformat(), "nota": cfdi.pago_manual_nota, "total": str(cfdi.total), "pagado_rep": str(pagado)},
    )
    return _con_estado_pago(db, empresa_id=ctx.empresa.id, cfdis=[cfdi])[0]


@router.delete("/{cfdi_id}/pago-manual", response_model=CfdiRead)
def quitar_pago_manual(
    cfdi_id: uuid.UUID,
    ctx: EmpresaContext = Depends(require_permissions("cfdi.editar")),
    db: Session = Depends(get_db),
) -> CfdiRead:
    cfdi = _factura(db, ctx=ctx, cfdi_id=cfdi_id)
    fecha_anterior = cfdi.pago_manual_fecha
    try:
        crud.quitar_pago_manual(db, cfdi=cfdi)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    bitacora_crud.registrar(
        db,
        empresa_id=ctx.empresa.id,
        usuario=ctx.usuario,
        accion="cfdi.pago_manual_quitado",
        descripcion=f"Se quitó la marca de pago a mano (del {fecha_anterior}) a la factura {cfdi.uuid_fiscal[:8]}…",
        entidad_tipo="cfdi",
        entidad_id=cfdi.id,
    )
    return _con_estado_pago(db, empresa_id=ctx.empresa.id, cfdis=[cfdi])[0]
