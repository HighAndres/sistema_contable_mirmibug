"""Seed idempotente de catálogos SAT (subconjunto real, no el listado completo).

Ejecutar DESPUÉS de aplicar las migraciones:
    PYTHONPATH=. python scripts/seed_catalogs.py
"""

from sqlalchemy import select

from app.db.session import SessionLocal
from app.modules.catalogs.models import Catalogo

CATALOGOS: dict[str, dict[str, str]] = {
    "regimen_fiscal": {
        "601": "General de Ley Personas Morales",
        "603": "Personas Morales con Fines no Lucrativos",
        "605": "Sueldos y Salarios e Ingresos Asimilados a Salarios",
        "606": "Arrendamiento",
        "612": "Personas Físicas con Actividades Empresariales y Profesionales",
        "621": "Incorporación Fiscal",
        "626": "Régimen Simplificado de Confianza (RESICO)",
    },
    "forma_pago": {
        "01": "Efectivo",
        "02": "Cheque nominativo",
        "03": "Transferencia electrónica de fondos",
        "04": "Tarjeta de crédito",
        "28": "Tarjeta de débito",
        "99": "Por definir",
    },
    "uso_cfdi": {
        "G01": "Adquisición de mercancías",
        "G03": "Gastos en general",
        "I01": "Construcciones",
        "P01": "Por definir",
        "S01": "Sin efectos fiscales",
        "CP01": "Pagos",
    },
    "unidad_medida": {
        "H87": "Pieza",
        "E48": "Unidad de servicio",
        "KGM": "Kilogramo",
        "LTR": "Litro",
        "ACT": "Actividad",
    },
}


def seed() -> None:
    db = SessionLocal()
    try:
        existentes = {(c.tipo, c.codigo): c for c in db.scalars(select(Catalogo)).all()}
        creados = 0
        for tipo, valores in CATALOGOS.items():
            for codigo, nombre in valores.items():
                if (tipo, codigo) not in existentes:
                    db.add(Catalogo(tipo=tipo, codigo=codigo, nombre=nombre))
                    creados += 1
        db.commit()
        print(f"Seed OK: {creados} valores nuevos de catálogo ({len(CATALOGOS)} tipos).")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
