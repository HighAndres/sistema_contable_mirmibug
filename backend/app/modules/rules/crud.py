import uuid

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.modules.cfdi.models import Cfdi
from app.modules.rules.engine import evaluar_cfdi
from app.modules.rules.models import CfdiAlerta


def list_alertas_de_cfdi(db: Session, *, cfdi_id: uuid.UUID) -> list[CfdiAlerta]:
    return list(db.scalars(select(CfdiAlerta).where(CfdiAlerta.cfdi_id == cfdi_id)))


def evaluar_cfdis(db: Session, cfdis: list[Cfdi]) -> int:
    """Re-evalúa las reglas sobre los CFDIs dados y reemplaza sus alertas. Devuelve el total generado."""
    if not cfdis:
        return 0

    cfdi_ids = [c.id for c in cfdis]
    db.execute(delete(CfdiAlerta).where(CfdiAlerta.cfdi_id.in_(cfdi_ids)))

    total = 0
    for cfdi in cfdis:
        for regla_codigo, severidad, detalle in evaluar_cfdi(cfdi):
            db.add(
                CfdiAlerta(
                    cfdi_id=cfdi.id, regla_codigo=regla_codigo, severidad=severidad, detalle=detalle
                )
            )
            total += 1

    db.commit()
    return total


def evaluar_empresa(db: Session, *, empresa_id: uuid.UUID) -> int:
    cfdis = list(db.scalars(select(Cfdi).where(Cfdi.empresa_id == empresa_id)))
    return evaluar_cfdis(db, cfdis)
