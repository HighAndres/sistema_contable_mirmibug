import uuid
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import EmpresaContext, require_permissions
from app.db.session import get_db
from app.modules.bitacora import crud as bitacora_crud
from app.modules.cfdi import crud, reportes
from app.modules.cfdi.models import Cfdi
from app.modules.cfdi.schemas import (
    CfdiConceptoRead,
    CfdiDetalleRead,
    CfdiPage,
    CfdiRead,
    CfdiResumen,
    ClasificacionMasivaRequest,
    ClasificacionMasivaResultado,
    ClasificacionRequest,
    PagoDoctoRead,
    PagoManualRequest,
    ReporteCfdi,
    ValoresClasificacion,
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
    clasificacion: str | None = Query(default=None, pattern="^(deducible|no_deducible|deduccion_personal|sin_clasificar)$"),
    concepto: str | None = Query(default=None, max_length=60, description="Concepto del papel de trabajo (contiene)"),
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
        "clasificacion": clasificacion,
        "concepto": concepto,
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


@router.get("/clasificacion/valores", response_model=ValoresClasificacion)
def valores_clasificacion(
    ctx: EmpresaContext = Depends(require_permissions("cfdi.leer")),
    db: Session = Depends(get_db),
) -> ValoresClasificacion:
    """Conceptos y cuentas contables ya usados en la empresa (para autocompletar
    al clasificar) y cuántas facturas vigentes siguen sin clasificar."""
    conceptos, cuentas, sin_clasificar = crud.valores_clasificacion(db, empresa_id=ctx.empresa.id)
    return ValoresClasificacion(conceptos=conceptos, cuentas_contables=cuentas, sin_clasificar=sin_clasificar)


@router.post("/clasificacion-masiva", response_model=ClasificacionMasivaResultado)
def clasificar_masivo(
    payload: ClasificacionMasivaRequest,
    ctx: EmpresaContext = Depends(require_permissions("cfdi.editar")),
    db: Session = Depends(get_db),
) -> ClasificacionMasivaResultado:
    """Aplica los campos indicados a varias facturas de golpe. Los que van en
    nulo no se tocan, para capturar por lotes sin pisar lo ya clasificado."""
    try:
        actualizados, omitidos = crud.clasificar_masivo(
            db,
            empresa_id=ctx.empresa.id,
            cfdi_ids=payload.cfdi_ids,
            clasificacion=payload.clasificacion,
            concepto=payload.concepto,
            cuenta_contable=payload.cuenta_contable,
            referencia_bancaria=payload.referencia_bancaria,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    campos = ", ".join(
        f"{k}={v}"
        for k, v in (
            ("clasificación", payload.clasificacion),
            ("concepto", payload.concepto),
            ("cuenta", payload.cuenta_contable),
            ("referencia", payload.referencia_bancaria),
        )
        if v is not None
    )
    bitacora_crud.registrar(
        db,
        empresa_id=ctx.empresa.id,
        usuario=ctx.usuario,
        accion="cfdi.clasificacion_masiva",
        descripcion=f"Clasificación aplicada a {actualizados} factura(s): {campos}",
        entidad_tipo="cfdi",
        metadatos={"actualizados": actualizados, "omitidos": omitidos, "solicitados": len(payload.cfdi_ids)},
    )
    return ClasificacionMasivaResultado(actualizados=actualizados, omitidos=omitidos)


@router.get("/reporte/{formato}", response_model=ReporteCfdi)
def reporte(
    formato: str,
    filtros: dict = Depends(_filtros),
    ctx: EmpresaContext = Depends(require_permissions("cfdi.leer")),
    db: Session = Depends(get_db),
) -> ReporteCfdi:
    """Reporte con el mismo layout que el contador baja hoy de su portal
    (ONEFACTURE / MiAdminPro), sobre TODOS los CFDI que cumplen los filtros de la
    lista — no solo la página visible. El formato `general` es, columna por
    columna, la hoja INGRESOS/GASTOS de sus papeles de trabajo, más las columnas
    que él captura a mano y que aquí ya vienen resueltas."""
    if formato not in reportes.FORMATOS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Formato desconocido. Disponibles: {', '.join(reportes.FORMATOS)}")
    extra = reportes.PERMISO_EXTRA.get(formato)
    if extra and extra not in ctx.permisos:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No tienes permisos para ver datos de nómina")
    tipo_forzado = reportes.TIPO_FORZADO.get(formato)
    if tipo_forzado:
        filtros = {**filtros, "tipo": tipo_forzado}
    filas, total = crud.filas_reporte(db, empresa_id=ctx.empresa.id, **filtros)
    columnas, valores, sin_dato = reportes.construir(formato, filas)
    return ReporteCfdi(
        formato=formato,
        descripcion=reportes.FORMATOS[formato],
        columnas=columnas,
        filas=valores,
        total=total,
        truncado=total > crud.TOPE_REPORTE,
        sin_dato=sin_dato,
    )


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


@router.put("/{cfdi_id}/clasificacion", response_model=CfdiRead)
def clasificar(
    cfdi_id: uuid.UUID,
    payload: ClasificacionRequest,
    ctx: EmpresaContext = Depends(require_permissions("cfdi.editar")),
    db: Session = Depends(get_db),
) -> CfdiRead:
    """Captura la clasificación del papel de trabajo sobre una factura: efecto
    fiscal (deducible / no deducible / deducción personal), concepto, cuenta
    contable y referencia bancaria. Un gasto no deducible o de deducción
    personal deja de restar en el ISR y su IVA deja de ser acreditable."""
    cfdi = _factura(db, ctx=ctx, cfdi_id=cfdi_id)
    anterior = cfdi.clasificacion
    try:
        crud.clasificar(
            db,
            cfdi=cfdi,
            clasificacion=payload.clasificacion,
            concepto=payload.concepto,
            cuenta_contable=payload.cuenta_contable,
            referencia_bancaria=payload.referencia_bancaria,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    folio = "-".join(filter(None, (cfdi.serie, cfdi.folio))) or f"{cfdi.uuid_fiscal[:8]}…"
    bitacora_crud.registrar(
        db,
        empresa_id=ctx.empresa.id,
        usuario=ctx.usuario,
        accion="cfdi.clasificacion",
        descripcion=f"Factura {folio}: clasificación {anterior or 'sin clasificar'} → {cfdi.clasificacion or 'sin clasificar'}"
        + (f" ({cfdi.concepto})" if cfdi.concepto else ""),
        entidad_tipo="cfdi",
        entidad_id=cfdi.id,
        metadatos={
            "clasificacion": cfdi.clasificacion,
            "concepto": cfdi.concepto,
            "cuenta_contable": cfdi.cuenta_contable,
            "referencia_bancaria": cfdi.referencia_bancaria,
        },
    )
    return _con_estado_pago(db, empresa_id=ctx.empresa.id, cfdis=[cfdi])[0]
