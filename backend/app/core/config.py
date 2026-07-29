from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import PostgresDsn, computed_field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# Raíz de backend/, para resolver el .env sin depender del directorio actual.
BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Configuración central de la app, leída desde variables de entorno / .env."""

    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---- App ----
    PROJECT_NAME: str = "Nubinox API"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    API_V1_PREFIX: str = "/api/v1"

    # ---- Seguridad / JWT ----
    SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    PASSWORD_RESET_TOKEN_EXPIRE_MINUTES: int = 30
    # Rol asignado por defecto a un usuario nuevo dentro de una empresa.
    DEFAULT_USER_ROLE: str = "contador"

    # ---- Bloqueo por intentos fallidos de login ----
    LOGIN_MAX_INTENTOS: int = 5
    LOGIN_BLOQUEO_MINUTOS: int = 15

    # ---- Frontend (para construir enlaces, p. ej. reset de contraseña) ----
    FRONTEND_URL: str = "http://localhost:3000"

    # ---- Base de datos ----
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "nubinox"

    # ---- CORS ----
    BACKEND_CORS_ORIGINS: Annotated[list[str], NoDecode] = []

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
    def _split_cors(cls, v: str | list[str]) -> list[str]:
        """Permite definir orígenes como cadena separada por comas en el .env."""
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    @computed_field  # type: ignore[prop-decorator]
    @property
    def DATABASE_URL(self) -> str:
        """URL de conexión SQLAlchemy (sync, psycopg2)."""
        return str(
            PostgresDsn.build(
                scheme="postgresql+psycopg2",
                username=self.POSTGRES_USER,
                password=self.POSTGRES_PASSWORD,
                host=self.POSTGRES_HOST,
                port=self.POSTGRES_PORT,
                path=self.POSTGRES_DB,
            )
        )


@lru_cache
def get_settings() -> Settings:
    """Cachea la instancia para no releer el entorno en cada import."""
    return Settings()


settings = get_settings()
