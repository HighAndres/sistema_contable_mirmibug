import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import EmpresaContext, require_permissions
from app.modules.sat import carga_xml, documentos
from app.db.session import get_db
from app.modules.bitacora import crud as bitacora_crud

router = APIRouter(prefix="/sat", tags=["sat"])


@router.post("/sincronizar")
def sincronizar(
    ctx: EmpresaContext = Depends(require_permissions("sat.sincronizar")),
    db: Session = Depends(get_db),
) -> dict[str, int]:
    """Sincronización incremental de CFDIs. Hoy usa el proveedor simulado; con la
    e.firma cargada usará la descarga masiva del SAT (ver sat/descarga.py)."""
    from app.modules.sat.descarga import obtener_proveedor

    r = obtener_proveedor("mock").sincronizar(db, empresa=ctx.empresa, desde=None, hasta=None)
    bitacora_crud.registrar(
        db,
        empresa_id=ctx.empresa.id,
        usuario=ctx.usuario,
        accion="sat.sincronizado",
        descripcion=f"Sincronización con el SAT: {r.cfdis_nuevos} CFDIs nuevos, {r.alertas_generadas} alertas generadas",
        metadatos={"cfdis_nuevos": r.cfdis_nuevos, "alertas_generadas": r.alertas_generadas},
    )
    return {"cfdis_nuevos": r.cfdis_nuevos, "alertas_generadas": r.alertas_generadas}


def _pdf(contenido: bytes, nombre: str) -> Response:
    return Response(content=contenido, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{nombre}"'})


@router.get("/constancia", response_class=Response)
def constancia_situacion_fiscal(
    ctx: EmpresaContext = Depends(require_permissions("empresas.leer")),
    db: Session = Depends(get_db),
) -> Response:
    """Constancia de situación fiscal (PDF simulado con los datos de la empresa)."""
    bitacora_crud.registrar(
        db, empresa_id=ctx.empresa.id, usuario=ctx.usuario, accion="sat.constancia",
        descripcion="Descarga de constancia de situación fiscal (simulada)",
    )
    return _pdf(documentos.constancia_situacion_fiscal(ctx.empresa), f"constancia_{ctx.empresa.rfc}.pdf")


@router.get("/opinion", response_class=Response)
def opinion_cumplimiento(
    sentido: str = Query(default="positivo", pattern="^(positivo|negativo)$"),
    ctx: EmpresaContext = Depends(require_permissions("empresas.leer")),
    db: Session = Depends(get_db),
) -> Response:
    """Opinión de cumplimiento de obligaciones (PDF simulado)."""
    bitacora_crud.registrar(
        db, empresa_id=ctx.empresa.id, usuario=ctx.usuario, accion="sat.opinion",
        descripcion=f"Descarga de opinión de cumplimiento (simulada, {sentido})",
    )
    return _pdf(documentos.opinion_cumplimiento(ctx.empresa, sentido=sentido), f"opinion_{ctx.empresa.rfc}.pdf")


class CargaXmlResponse(BaseModel):
    nuevos: int
    duplicados: int
    ajenos: int
    alertas: int
    errores: list[dict]


MAX_XML_TOTAL = 50 * 1024 * 1024


@router.post("/cargar-xml", response_model=CargaXmlResponse)
async def cargar_xml(
    archivos: list[UploadFile] = File(..., description="Uno o varios .xml, o .zip con XML"),
    ctx: EmpresaContext = Depends(require_permissions("sat.sincronizar")),
    db: Session = Depends(get_db),
) -> CargaXmlResponse:
    """Carga CFDI reales a la bóveda (XML sueltos o ZIP). Deduplica por UUID,
    clasifica emitido/recibido por RFC de la empresa, liga los complementos de
    pago a sus facturas PPD y corre el motor de reglas."""
    pares = []
    total = 0
    for a in archivos:
        contenido = await a.read()
        total += len(contenido)
        if total > MAX_XML_TOTAL:
            raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "La carga supera 50 MB")
        pares.append((a.filename or "archivo", contenido))
    r = carga_xml.cargar_archivos(db, empresa=ctx.empresa, archivos=pares)
    bitacora_crud.registrar(
        db, empresa_id=ctx.empresa.id, usuario=ctx.usuario, accion="sat.xml_cargado",
        descripcion=f"Carga de XML: {r.nuevos} CFDI nuevos, {r.duplicados} duplicados, {r.ajenos} ajenos, {len(r.errores)} con error, {r.alertas} alertas",
        metadatos={"archivos": [a.filename for a in archivos], "nuevos": r.nuevos},
    )
    return CargaXmlResponse(nuevos=r.nuevos, duplicados=r.duplicados, ajenos=r.ajenos, alertas=r.alertas, errores=r.errores)


@router.get("/xml/{cfdi_id}", response_class=Response)
def descargar_xml(cfdi_id: uuid.UUID, ctx: EmpresaContext = Depends(require_permissions("cfdi.leer")), db: Session = Depends(get_db)) -> Response:
    """XML original del CFDI (solo los cargados/descargados; los simulados no tienen)."""
    from app.modules.cfdi import crud as cfdi_crud

    c = cfdi_crud.get(db, empresa_id=ctx.empresa.id, cfdi_id=cfdi_id)
    if c is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "CFDI no encontrado")
    if not c.xml:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Este CFDI es simulado y no tiene XML original")
    return Response(content=c.xml.encode("utf-8"), media_type="application/xml", headers={"Content-Disposition": f'attachment; filename="{c.uuid_fiscal}.xml"'})
