import random

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import EmpresaContext, require_permissions
from app.db.session import get_db
from app.modules.bitacora import crud as bitacora_crud
from app.modules.rules import crud as rules_crud
from app.modules.sat.mock_generator import generar_cfdis_mock

router = APIRouter(prefix="/sat", tags=["sat"])


@router.post("/sincronizar")
def sincronizar(
    ctx: EmpresaContext = Depends(require_permissions("sat.sincronizar")),
    db: Session = Depends(get_db),
) -> dict[str, int]:
    """Simula una sincronización incremental de CFDIs con el SAT."""
    cantidad = random.randint(5, 15)
    nuevos = generar_cfdis_mock(db, empresa=ctx.empresa, cantidad=cantidad, dias_atras=30)
    alertas = rules_crud.evaluar_cfdis(db, nuevos)

    bitacora_crud.registrar(
        db,
        empresa_id=ctx.empresa.id,
        usuario=ctx.usuario,
        accion="sat.sincronizado",
        descripcion=f"Sincronización con el SAT: {len(nuevos)} CFDIs nuevos, {alertas} alertas generadas",
        metadatos={"cfdis_nuevos": len(nuevos), "alertas_generadas": alertas},
    )
    return {"cfdis_nuevos": len(nuevos), "alertas_generadas": alertas}
