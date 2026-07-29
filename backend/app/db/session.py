from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

# Engine sync con psycopg2. pool_pre_ping evita conexiones muertas.
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    echo=False,
    future=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
    class_=Session,
)


def get_db() -> Generator[Session, None, None]:
    """Dependencia FastAPI: abre una sesión por request y la cierra al final."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
