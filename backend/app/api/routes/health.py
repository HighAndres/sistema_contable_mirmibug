from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.session import get_db

router = APIRouter(tags=["health"])


@router.get("/health", summary="Liveness check")
def health() -> dict[str, str]:
    """Responde siempre que el proceso esté vivo (no toca la DB)."""
    return {"status": "ok"}


@router.get("/health/db", summary="Readiness check (DB)")
def health_db(db: Session = Depends(get_db)) -> dict[str, str]:
    """Verifica que la conexión a PostgreSQL funcione."""
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No se pudo conectar a la base de datos",
        ) from exc
    return {"status": "ok", "database": "ok"}
