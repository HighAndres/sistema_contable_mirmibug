import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class BitacoraRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    usuario_email: str
    accion: str
    descripcion: str
    entidad_tipo: str | None
    entidad_id: str | None
    created_at: datetime
