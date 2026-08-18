import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class CredencialConectarRequest(BaseModel):
    tipo: str = "ciec"


class CredencialRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    empresa_id: uuid.UUID
    tipo: str
    estado: str
    conectado_at: datetime | None


class VigenciaCertificado(BaseModel):
    tipo: str  # fiel | csd
    numero_serie: str | None
    vence: date | None
    dias_restantes: int | None
    estado: str  # sin_datos | vencida | por_vencer | vigente


class VigenciasRead(BaseModel):
    conectado: bool
    fiel: VigenciaCertificado
    csd: VigenciaCertificado
