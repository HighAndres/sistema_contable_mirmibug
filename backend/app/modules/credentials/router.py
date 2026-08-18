from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import EmpresaContext, get_current_empresa, require_permissions
from app.db.session import get_db
from app.modules.bitacora import crud as bitacora_crud
from app.modules.credentials import crud
from app.modules.credentials.schemas import CredencialConectarRequest, CredencialRead, VigenciaCertificado, VigenciasRead

router = APIRouter(prefix="/credentials", tags=["credentials"])


@router.get("", response_model=CredencialRead | None)
def estado_credencial(
    ctx: EmpresaContext = Depends(get_current_empresa),
    db: Session = Depends(get_db),
) -> CredencialRead | None:
    return crud.get_por_empresa(db, ctx.empresa.id)


@router.post("/conectar", response_model=CredencialRead)
def conectar_sat(
    payload: CredencialConectarRequest,
    ctx: EmpresaContext = Depends(require_permissions("credenciales.gestionar")),
    db: Session = Depends(get_db),
) -> CredencialRead:
    credencial = crud.conectar(db, empresa_id=ctx.empresa.id, tipo=payload.tipo)
    bitacora_crud.registrar(
        db,
        empresa_id=ctx.empresa.id,
        usuario=ctx.usuario,
        accion="sat.conectado",
        descripcion=f"Conexión con el SAT establecida ({payload.tipo.upper()})",
    )
    return credencial


@router.get("/vigencias", response_model=VigenciasRead)
def vigencias(
    ctx: EmpresaContext = Depends(get_current_empresa),
    db: Session = Depends(get_db),
) -> VigenciasRead:
    """Vigencia de la e.firma (FIEL) y del sello (CSD) de la empresa, con aviso
    cuando faltan 60 días o menos."""
    c = crud.get_por_empresa(db, ctx.empresa.id)

    def cert(tipo: str, serie, vence) -> VigenciaCertificado:
        estado, dias = crud.estado_vigencia(vence)
        return VigenciaCertificado(tipo=tipo, numero_serie=serie, vence=vence, dias_restantes=dias, estado=estado)

    if c is None:
        return VigenciasRead(conectado=False, fiel=cert("fiel", None, None), csd=cert("csd", None, None))
    return VigenciasRead(
        conectado=c.estado == "conectado",
        fiel=cert("fiel", c.fiel_numero_serie, c.fiel_vigencia_hasta),
        csd=cert("csd", c.csd_numero_serie, c.csd_vigencia_hasta),
    )
