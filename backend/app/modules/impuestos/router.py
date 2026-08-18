"""IVA base flujo e ISR provisional por periodo, y configuración fiscal de la empresa.

Permisos: impuestos.leer (ver) · empresas.editar (configuración fiscal).
"""

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import EmpresaContext, require_permissions
from app.db.session import get_db
from app.modules.bitacora import crud as bitacora_crud
from app.modules.impuestos import calculos, crud
from app.modules.impuestos.schemas import (
    ConfiguracionFiscalRead,
    ConfiguracionFiscalUpdate,
    DesgloseIvaRead,
    IsrRead,
    IvaRead,
    MesIsrRead,
)

router = APIRouter(prefix="/impuestos", tags=["impuestos"])


@router.get("/iva", response_model=IvaRead)
def iva(
    anio: int = Query(default=None, ge=2000, le=2100),
    mes: int | None = Query(default=None, ge=1, le=12, description="Vacío = anual"),
    ctx: EmpresaContext = Depends(require_permissions("impuestos.leer")),
    db: Session = Depends(get_db),
) -> IvaRead:
    """Previa de IVA en base a flujo: trasladado efectivamente cobrado (PUE + REP
    emitidos) menos acreditable efectivamente pagado (PUE + REP recibidos)."""
    anio = anio or date.today().year
    r = crud.iva_periodo(db, empresa_id=ctx.empresa.id, anio=anio, mes=mes)
    conv = lambda filas: [DesgloseIvaRead(concepto=f.concepto, num_cfdis=f.num_cfdis, base=float(f.base), iva=float(f.iva)) for f in filas]  # noqa: E731
    return IvaRead(
        anio=anio,
        mes=mes,
        trasladado_cobrado=float(r.trasladado_cobrado),
        acreditable_pagado=float(r.acreditable_pagado),
        saldo=float(r.saldo),
        trasladado_ppd_pendiente=float(r.trasladado_ppd_pendiente),
        acreditable_ppd_pendiente=float(r.acreditable_ppd_pendiente),
        emitidas=conv(r.emitidas),
        recibidas=conv(r.recibidas),
        anios_disponibles=crud.anios_con_datos(db, empresa_id=ctx.empresa.id),
    )


@router.get("/isr", response_model=IsrRead)
def isr(
    anio: int = Query(default=None, ge=2000, le=2100),
    hasta_mes: int | None = Query(default=None, ge=1, le=12, description="Vacío = mes actual (o diciembre si es un año pasado)"),
    ctx: EmpresaContext = Depends(require_permissions("impuestos.leer")),
    db: Session = Depends(get_db),
) -> IsrRead:
    hoy = date.today()
    anio = anio or hoy.year
    if hasta_mes is None:
        hasta_mes = hoy.month if anio == hoy.year else 12
    r = crud.isr_ejercicio(db, empresa=ctx.empresa, anio=anio, hasta_mes=hasta_mes)
    return IsrRead(
        anio=anio,
        hasta_mes=hasta_mes,
        mecanica=r.mecanica,
        descripcion=r.descripcion,
        tipo_persona=ctx.empresa.tipo_persona,
        regimen_fiscal_codigo=ctx.empresa.regimen_fiscal_codigo,
        coeficiente_utilidad=float(ctx.empresa.coeficiente_utilidad) if ctx.empresa.coeficiente_utilidad is not None else None,
        meses=[
            MesIsrRead(
                mes=m.mes,
                ingresos_mes=float(m.ingresos_mes),
                deducciones_mes=float(m.deducciones_mes),
                ingresos_acumulados=float(m.ingresos_acumulados),
                deducciones_acumuladas=float(m.deducciones_acumuladas),
                base=float(m.base),
                tasa_aplicada=float(m.tasa_aplicada) if m.tasa_aplicada is not None else None,
                isr_acumulado=float(m.isr_acumulado),
                pagos_anteriores=float(m.pagos_anteriores),
                isr_del_mes=float(m.isr_del_mes),
            )
            for m in r.meses
        ],
        advertencias=r.advertencias,
        anios_disponibles=crud.anios_con_datos(db, empresa_id=ctx.empresa.id),
    )


def _config(ctx: EmpresaContext) -> ConfiguracionFiscalRead:
    e = ctx.empresa
    return ConfiguracionFiscalRead(
        rfc=e.rfc,
        razon_social=e.razon_social,
        tipo_persona=e.tipo_persona,
        regimen_fiscal_codigo=e.regimen_fiscal_codigo,
        coeficiente_utilidad=float(e.coeficiente_utilidad) if e.coeficiente_utilidad is not None else None,
        mecanica_isr=calculos.clasificar_regimen(tipo_persona=e.tipo_persona, regimen_codigo=e.regimen_fiscal_codigo),
    )


@router.get("/configuracion", response_model=ConfiguracionFiscalRead)
def configuracion(ctx: EmpresaContext = Depends(require_permissions("impuestos.leer"))) -> ConfiguracionFiscalRead:
    return _config(ctx)


@router.put("/configuracion", response_model=ConfiguracionFiscalRead)
def actualizar_configuracion(
    payload: ConfiguracionFiscalUpdate,
    ctx: EmpresaContext = Depends(require_permissions("empresas.editar")),
    db: Session = Depends(get_db),
) -> ConfiguracionFiscalRead:
    cambios = payload.model_dump(exclude_unset=True)
    for k, v in cambios.items():
        setattr(ctx.empresa, k, v)
    db.commit()
    db.refresh(ctx.empresa)
    bitacora_crud.registrar(
        db,
        empresa_id=ctx.empresa.id,
        usuario=ctx.usuario,
        accion="empresa.config_fiscal",
        descripcion=f"Configuración fiscal actualizada: {', '.join(f'{k}={v}' for k, v in cambios.items())}",
        entidad_tipo="empresa",
        entidad_id=ctx.empresa.id,
        metadatos={k: (str(v) if v is not None else None) for k, v in cambios.items()},
    )
    return _config(ctx)
