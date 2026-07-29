import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CredencialConectarRequest(BaseModel):
    tipo: str = "ciec"


class CredencialRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    empresa_id: uuid.UUID
    tipo: str
    estado: str
    conectado_at: datetime | None
