import random
import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.credentials.models import CredencialSat


def get_por_empresa(db: Session, empresa_id: uuid.UUID) -> CredencialSat | None:
    return db.scalar(select(CredencialSat).where(CredencialSat.empresa_id == empresa_id))


def conectar(db: Session, *, empresa_id: uuid.UUID, tipo: str) -> CredencialSat:
    """Simula la conexión con el SAT: no valida credenciales reales."""
    credencial = get_por_empresa(db, empresa_id)
    if credencial is None:
        credencial = CredencialSat(empresa_id=empresa_id, tipo=tipo)
        db.add(credencial)

    credencial.tipo = tipo
    credencial.estado = "conectado"
    credencial.conectado_at = datetime.now(timezone.utc)
    # Vigencias simuladas: la e.firma dura 4 años y el CSD 4 años desde su
    # emisión; aquí se simula que se emitieron hace un tiempo aleatorio para
    # que la demo muestre distintos estados (vigente / por vencer).
    rng = random.Random(str(empresa_id))
    hoy = date.today()
    if credencial.fiel_vigencia_hasta is None:
        credencial.fiel_numero_serie = "3000100000040" + "".join(rng.choices("0123456789", k=7))
        credencial.fiel_vigencia_hasta = hoy + timedelta(days=rng.randint(20, 4 * 365))
    if credencial.csd_vigencia_hasta is None:
        credencial.csd_numero_serie = "3000100000050" + "".join(rng.choices("0123456789", k=7))
        credencial.csd_vigencia_hasta = hoy + timedelta(days=rng.randint(60, 4 * 365))
    db.commit()
    db.refresh(credencial)
    return credencial


DIAS_AVISO_VENCIMIENTO = 60


def estado_vigencia(vence: date | None, *, hoy: date | None = None) -> tuple[str, int | None]:
    """(estado, días restantes): sin_datos | vencida | por_vencer | vigente."""
    if vence is None:
        return "sin_datos", None
    hoy = hoy or date.today()
    dias = (vence - hoy).days
    if dias < 0:
        return "vencida", dias
    if dias <= DIAS_AVISO_VENCIMIENTO:
        return "por_vencer", dias
    return "vigente", dias
