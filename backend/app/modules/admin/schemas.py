import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.modules.auth.schemas import PASSWORD_MIN_LENGTH


class UsuarioAdminRead(BaseModel):
    id: uuid.UUID
    email: str
    nombre_completo: str | None
    is_active: bool
    is_superadmin: bool
    num_empresas: int
    created_at: datetime


class UsuarioAdminCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=PASSWORD_MIN_LENGTH)
    nombre_completo: str | None = None
    is_superadmin: bool = False
