import re
import uuid
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.modules.impuestos.regimenes import validar_regimen

# RFC: 3 letras (PM) o 4 (PF) + fecha AAMMDD + homoclave de 3.
RFC_RE = re.compile(r"^[A-ZÑ&]{3,4}[0-9]{6}[A-Z0-9]{3}$")


class EmpresaCreate(BaseModel):
    rfc: str = Field(min_length=12, max_length=13)
    razon_social: str = Field(min_length=1, max_length=255)
    # Obligatorio desde el alta (acuerdo 2026-09-07): de él depende la
    # mecánica de ISR que el sistema aplica automáticamente.
    regimen_fiscal_codigo: str = Field(max_length=10)
    # Solo tiene sentido para personas morales del régimen general.
    coeficiente_utilidad: Decimal | None = Field(default=None, ge=0, le=1)

    @field_validator("rfc")
    @classmethod
    def _rfc_valido(cls, v: str) -> str:
        v = v.strip().upper()
        if not RFC_RE.match(v):
            raise ValueError("RFC inválido: 12 caracteres para persona moral o 13 para persona física (p. ej. ABC010101XY1)")
        return v

    @field_validator("coeficiente_utilidad")
    @classmethod
    def _cuatro_decimales(cls, v: Decimal | None) -> Decimal | None:
        return v.quantize(Decimal("0.0001")) if v is not None else None

    @model_validator(mode="after")
    def _regimen_coherente(self) -> "EmpresaCreate":
        error = validar_regimen(rfc=self.rfc, regimen_codigo=self.regimen_fiscal_codigo)
        if error:
            raise ValueError(error)
        return self


class RegimenFiscalRead(BaseModel):
    codigo: str
    nombre: str
    tipos_persona: list[str]  # ["fisica"], ["moral"] o ambos
    mecanica_isr: str


class EmpresaRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    rfc: str
    razon_social: str
    regimen_fiscal_codigo: str | None
    tipo_persona: str = "moral"
    coeficiente_utilidad: float | None = None
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
