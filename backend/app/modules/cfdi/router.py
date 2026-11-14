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
    DesgloseImpuestoRead,
    LigaBancariaRead,
    NominaConceptoRead,
    NominaDetalleRead,
    PagoDoctoRead,
    PagoManualRequest,
    ReporteCfdi,
    TasaIvaRead,
    ValoresClasificacion,
    ValoresFiltros,
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
    uso_cfdi: str | None = Query(default=None, max_length=5),
    registro_patronal: str | None = Query(default=None, max_length=20, description="Solo recibos de nómina"),
    entidad: str | None = Query(default=None, max_length=5, description="Clave de entidad federativa del complemento de nómina"),
    periodicidad: str | None = Query(default=None, max_length=5, description="Periodicidad de pago del complemento de nómina"),
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
        "uso_cfdi": uso_cfdi,
        "registro_patronal": registro_patronal,
        "entidad": entidad,
        "periodicidad": periodicidad,
    }


def _desglose_iva(c: Cfdi) -> list[TasaIvaRead]:
    """IVA trasladado por tasa, a partir de cfdi_impuestos. En un REP, el IVA
    pagado viene de los documentos relacionados (TrasladoDR)."""
    if c.tipo == "pago":
        iva = sum((Decimal(p.iva_pagado or 0) for p in c.pagos_relacionados), Decimal("0"))
        return [TasaIvaRead(etiqueta="IVA pagado", base=0, importe=float(iva))] if iva else []
    filas: dict[str, TasaIvaRead] = {}
    for i in c.impuestos:
        if i.impuesto != "002" or i.naturaleza != "traslado":
            continue
        etiqueta = "Exento" if (i.tipo_factor or "").lower() == "exento" else f"{float(i.tasa or 0) * 100:g}%"
        fila = filas.setdefault(etiqueta, TasaIvaRead(etiqueta=etiqueta, base=0, importe=0))
        fila.base += float(i.base or 0)
        fila.importe += float(i.importe or 0)
    return list(filas.values())


def _en_declaracion(c: Cfdi, estado_pago: str | None, conciliado: str | None) -> bool | None:
    """Si el comprobante cuenta para la declaración del periodo: vigente, que el
    contador no lo marcara como no deducible / deducción personal, y con el pago
    hecho (PUE, REP completo, pago manual) o conciliado en banco. El REP y la
    nómina no se marcan: van por su propia vía en los impuestos."""
    if c.tipo not in ("ingreso", "egreso", "nota_credito"):
        return None
    if c.estatus != "vigente" or not c.deducible:
        return False
    if c.tipo == "nota_credito":
        return True
    return estado_pago == "pagada" or conciliado == "conciliado"


def _con_estado_pago(db: Session, *, empresa_id: uuid.UUID, cfdis: list[Cfdi]) -> list[CfdiRead]:
    """Convierte a CfdiRead agregando los derivados: lo pagado por REP, el estado
    de pago, lo conciliado en banco, el desglose de IVA y los datos de REP/nómina."""
    pagado = crud.pagado_rep_de(db, empresa_id=empresa_id, uuids=[c.uuid_fiscal for c in cfdis if c.metodo_pago_codigo == "PPD"])
    ligado = crud.conciliado_de(db, cfdi_ids=[c.id for c in cfdis])
    out = []
    for c in cfdis:
        p = pagado.get(c.uuid_fiscal, Decimal("0"))
        importe_ligado = ligado.get(c.id, Decimal("0"))
        estado_pago = crud.estado_pago_de(c, p)
        conciliado = crud.estado_conciliado(c, importe_ligado)
        extra: dict = {
            "estado_pago": estado_pago,
            "pagado_rep": float(p),
            "conciliado": conciliado,
            "conciliado_importe": float(importe_ligado),
            "en_declaracion": _en_declaracion(c, estado_pago, conciliado),
            "desglose_iva": _desglose_iva(c),
        }
        if c.tipo == "pago" and c.pagos_relacionados:
            fechas = [d.fecha_pago for d in c.pagos_relacionados if d.fecha_pago]
            extra.update(
                rep_fecha_pago=max(fechas) if fechas else None,
                rep_importe_pagado=float(sum((Decimal(d.imp_pagado or 0) for d in c.pagos_relacionados), Decimal("0"))),
                rep_iva_pagado=float(sum((Decimal(d.iva_pagado or 0) for d in c.pagos_relacionados), Decimal("0"))),
            )
        if c.tipo == "nomina" and c.nomina is not None:
            n = c.nomina
            extra.update(
                nomina_fecha_pago=n.fecha_pago,
                nomina_percepciones=float(n.total_percepciones),
                nomina_deducciones=float(n.total_deducciones),
                nomina_otros_pagos=float(n.total_otros_pagos),
                registro_patronal=n.registro_patronal,
                entidad_codigo=n.clave_ent_fed,
                periodicidad_codigo=n.periodicidad_pago,
            )
        base = CfdiRead.model_validate(c, from_attributes=True)
        out.append(base.model_copy(update=extra))
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


@router.get("/filtros/valores", response_model=ValoresFiltros)
def valores_filtros(
    ctx: EmpresaContext = Depends(require_permissions("cfdi.leer")),
    db: Session = Depends(get_db),
) -> ValoresFiltros:
    """Valores presentes en los CFDI de la empresa para poblar los filtros de la
    lista: usos de CFDI y registro patronal / entidad / periodicidad de nómina."""
    return ValoresFiltros(**crud.valores_filtros(db, empresa_id=ctx.empresa.id))


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
    # Para "ir directo" del REP a las facturas que liquida: id de cada factura
    # relacionada que esté en la bóveda, resuelto en una sola consulta.
    from sqlalchemy import select as sa_select

    from app.modules.cfdi.models import Cfdi as CfdiModel

    uuids_relacionados = [p.uuid_relacionado for p in cfdi.pagos_relacionados]
    ids_por_uuid: dict[str, uuid.UUID] = {}
    if uuids_relacionados:
        ids_por_uuid = dict(
            db.execute(
                sa_select(CfdiModel.uuid_fiscal, CfdiModel.id).where(
                    CfdiModel.empresa_id == ctx.empresa.id, CfdiModel.uuid_fiscal.in_(uuids_relacionados)
                )
            ).all()
        )
    pagos_relacionados = [
        PagoDoctoRead(
            cfdi_pago_id=p.cfdi_pago_id, uuid_pago=cfdi.uuid_fiscal, uuid_relacionado=p.uuid_relacionado,
            cfdi_relacionado_id=ids_por_uuid.get(p.uuid_relacionado),
            num_parcialidad=p.num_parcialidad, imp_saldo_anterior=p.imp_saldo_anterior, imp_pagado=p.imp_pagado,
            imp_saldo_insoluto=p.imp_saldo_insoluto, iva_pagado=p.iva_pagado, fecha_pago=p.fecha_pago, forma_pago_codigo=p.forma_pago_codigo,
        )
        for p in cfdi.pagos_relacionados
    ]
    saldo = None
    if cfdi.metodo_pago_codigo == "PPD":
        # Marcada a mano = saldada, aunque no haya REP que la cubra.
        saldo = 0.0 if cfdi.pagada_manualmente else float(cfdi.total) - float(sum((p.imp_pagado for p in pagos_recibidos), 0))

    # Movimientos bancarios ligados en la conciliación (para mostrar el estatus
    # y comparar las fechas del estado de cuenta contra el complemento).
    from app.modules.conciliacion.models import LigaConciliacion

    ligas_bancarias = [
        LigaBancariaRead(
            movimiento_id=liga.movimiento_id,
            fecha=liga.movimiento.fecha,
            concepto=liga.movimiento.concepto,
            referencia=liga.movimiento.referencia,
            cuenta=liga.movimiento.cuenta.alias,
            importe=float(liga.importe),
        )
        for liga in db.scalars(sa_select(LigaConciliacion).where(LigaConciliacion.cfdi_id == cfdi.id))
    ]

    # Complemento de nómina. CURP, NSS, cuenta bancaria y salarios de cotización
    # solo con el permiso nomina.leer (mismo criterio que los reportes).
    nomina = None
    if cfdi.nomina is not None:
        n = cfdi.nomina
        sensibles = (
            {
                "curp_receptor": n.curp_receptor,
                "num_seguridad_social": n.num_seguridad_social,
                "banco": n.banco,
                "cuenta_bancaria": n.cuenta_bancaria,
                "salario_base_cot_apor": float(n.salario_base_cot_apor) if n.salario_base_cot_apor is not None else None,
                "salario_diario_integrado": float(n.salario_diario_integrado) if n.salario_diario_integrado is not None else None,
            }
            if "nomina.leer" in ctx.permisos
            else {}
        )
        nomina = NominaDetalleRead(
            tipo_nomina=n.tipo_nomina,
            fecha_pago=n.fecha_pago,
            fecha_inicial_pago=n.fecha_inicial_pago,
            fecha_final_pago=n.fecha_final_pago,
            num_dias_pagados=float(n.num_dias_pagados) if n.num_dias_pagados is not None else None,
            total_percepciones=float(n.total_percepciones),
            total_deducciones=float(n.total_deducciones),
            total_otros_pagos=float(n.total_otros_pagos),
            registro_patronal=n.registro_patronal,
            periodicidad_pago=n.periodicidad_pago,
            clave_ent_fed=n.clave_ent_fed,
            num_empleado=n.num_empleado,
            departamento=n.departamento,
            puesto=n.puesto,
            conceptos=[NominaConceptoRead.model_validate(cn, from_attributes=True) for cn in n.conceptos],
            **sensibles,
        )

    base = _con_estado_pago(db, empresa_id=ctx.empresa.id, cfdis=[cfdi])[0]
    return CfdiDetalleRead(
        **base.model_dump(),
        conceptos=[CfdiConceptoRead.model_validate(c, from_attributes=True) for c in cfdi.conceptos],
        alertas=alertas,
        pagos_recibidos=pagos_recibidos,
        pagos_relacionados=pagos_relacionados,
        saldo_pendiente=saldo,
        tiene_xml=bool(cfdi.xml),
        impuestos=[DesgloseImpuestoRead.model_validate(i, from_attributes=True) for i in cfdi.impuestos],
        ligas_bancarias=ligas_bancarias,
        nomina=nomina,
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
