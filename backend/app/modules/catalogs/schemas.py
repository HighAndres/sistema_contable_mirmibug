import uuid

from pydantic import BaseModel, ConfigDict


class CatalogoRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tipo: str
    codigo: str
    nombre: str
    activo: bool
