"""Crea la base de datos de la app si no existe. Lee credenciales del .env."""
import psycopg2

from app.core.config import settings

target = settings.POSTGRES_DB

conn = psycopg2.connect(
    dbname="postgres",
    user=settings.POSTGRES_USER,
    password=settings.POSTGRES_PASSWORD,
    host=settings.POSTGRES_HOST,
    port=settings.POSTGRES_PORT,
)
conn.autocommit = True
try:
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (target,))
    if cur.fetchone():
        print(f"La base '{target}' ya existe.")
    else:
        cur.execute(f'CREATE DATABASE "{target}"')
        print(f"Base '{target}' creada.")
finally:
    conn.close()
