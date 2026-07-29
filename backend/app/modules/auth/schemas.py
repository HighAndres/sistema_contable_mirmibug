import uuid

from pydantic import BaseModel, ConfigDict, EmailStr, Field

# Longitud mínima de contraseña, aplicada server-side (el frontend valida
# igual, pero eso es UX — la garantía real de seguridad vive aquí).
PASSWORD_MIN_LENGTH = 8


class UsuarioCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=PASSWORD_MIN_LENGTH)
    nombre_completo: str | None = None


class UsuarioRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    nombre_completo: str | None
    is_active: bool
    is_superadmin: bool


class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=PASSWORD_MIN_LENGTH)


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=PASSWORD_MIN_LENGTH)
