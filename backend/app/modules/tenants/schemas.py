import uuid

from pydantic import BaseModel, ConfigDict, EmailStr


class EmpresaCreate(BaseModel):
    rfc: str
    razon_social: str
    regimen_fiscal_codigo: str | None = None


class EmpresaRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    rfc: str
    razon_social: str
    regimen_fiscal_codigo: str | None
    activo: bool


class MiEmpresaRead(BaseModel):
    empresa: EmpresaRead
    rol: str
    permisos: list[str]


class MiembroEmpresaRead(BaseModel):
    usuario_id: uuid.UUID
    email: str
    nombre_completo: str | None
    rol: str
    is_active: bool


class InvitarUsuarioRequest(BaseModel):
    email: EmailStr
    rol_nombre: str
    nombre_completo: str | None = None


class InvitarUsuarioResponse(BaseModel):
    email: str
    rol: str
    usuario_nuevo: bool
    # Solo viene si se creó una cuenta nueva (no existía ya en el sistema).
    # Se muestra al admin que invita (acción autenticada y privilegiada), a
    # diferencia del token de /forgot-password que nunca se devuelve en la
    # respuesta por ser un endpoint público sin autenticación.
    password_temporal: str | None = None
