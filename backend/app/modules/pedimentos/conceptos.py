"""Catálogo concepto → clave SAT (por empresa) y su carga masiva desde Excel."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.pedimentos.models import ConceptoClaveSat, Pedimento
from app.utils import tabular

SINONIMOS = {
    "concepto": ["concepto", "descripcion", "producto", "mercancia", "nombre"],
    "clave": ["clave", "clave sat", "clave prodserv", "claveprodserv", "c_claveprodserv", "clave producto", "codigo sat"],
    "unidad": ["unidad", "clave unidad", "claveunidad", "c_claveunidad", "umc facturar", "facturar"],
}
COLUMNAS_PLANTILLA = ["Concepto", "Clave SAT (c_ClaveProdServ)", "Clave unidad SAT (opcional)"]


def normalizar(texto: str) -> str:
    return tabular.norm(texto).upper()


@dataclass
class ResultadoCarga:
    creados: int
    actualizados: int
    errores: list[dict]  # {"fila": n, "error": "..."}


def buscar_clave(db: Session, *, empresa_id: uuid.UUID, descripcion: str) -> ConceptoClaveSat | None:
    return db.scalar(
        select(ConceptoClaveSat).where(ConceptoClaveSat.empresa_id == empresa_id, ConceptoClaveSat.concepto_norm == normalizar(descripcion))
    )


def mapa_claves(db: Session, *, empresa_id: uuid.UUID) -> dict[str, ConceptoClaveSat]:
    return {c.concepto_norm: c for c in db.scalars(select(ConceptoClaveSat).where(ConceptoClaveSat.empresa_id == empresa_id))}


def listar(db: Session, *, empresa_id: uuid.UUID, q: str | None = None, limit: int = 200) -> tuple[list[ConceptoClaveSat], int]:
    stmt = select(ConceptoClaveSat).where(ConceptoClaveSat.empresa_id == empresa_id)
    if q:
        stmt = stmt.where(ConceptoClaveSat.concepto_norm.contains(normalizar(q)))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    return list(db.scalars(stmt.order_by(ConceptoClaveSat.concepto).limit(limit))), total


def upsert(db: Session, *, empresa_id: uuid.UUID, concepto: str, clave: str, unidad: str | None = None) -> tuple[ConceptoClaveSat, bool]:
    norm = normalizar(concepto)
    c = db.scalar(select(ConceptoClaveSat).where(ConceptoClaveSat.empresa_id == empresa_id, ConceptoClaveSat.concepto_norm == norm))
    creado = c is None
    if c is None:
        c = ConceptoClaveSat(empresa_id=empresa_id, concepto=concepto.strip()[:255], concepto_norm=norm[:255])
        db.add(c)
    c.clave_prodserv = clave
    if unidad:
        c.clave_unidad_sat = unidad
    return c, creado


def importar_excel(db: Session, *, empresa_id: uuid.UUID, contenido: bytes, nombre: str) -> ResultadoCarga:
    tabla = [r for r in tabular.leer_tabla(contenido, nombre) if r and any(v not in (None, "") for v in r)]
    idx, mapa = tabular.localizar_encabezado(tabla, SINONIMOS, {"concepto", "clave"})
    creados = actualizados = 0
    errores: list[dict] = []
    vistos: set[str] = set()
    for n, fila in enumerate(tabla[idx + 1 :], start=idx + 2):
        concepto = tabular.texto(tabular.celda(fila, mapa, "concepto"))
        clave_raw = tabular.celda(fila, mapa, "clave")
        unidad = tabular.texto(tabular.celda(fila, mapa, "unidad"))
        if not concepto:
            continue
        clave = tabular.texto(int(clave_raw) if isinstance(clave_raw, float) and clave_raw.is_integer() else clave_raw)
        if not clave or not clave.isdigit() or len(clave) != 8:
            errores.append({"fila": n, "concepto": concepto, "error": f"Clave SAT inválida: {clave!r} (deben ser 8 dígitos)"})
            continue
        norm = normalizar(concepto)
        if norm in vistos:
            errores.append({"fila": n, "concepto": concepto, "error": "Concepto repetido en el archivo; se conserva la primera fila"})
            continue
        vistos.add(norm)
        _, creado = upsert(db, empresa_id=empresa_id, concepto=concepto, clave=clave, unidad=unidad)
        creados += creado
        actualizados += not creado
    db.commit()
    return ResultadoCarga(creados=creados, actualizados=actualizados, errores=errores)


def aplicar_a_pedimento(db: Session, *, pedimento: Pedimento) -> int:
    """Rellena clave_prodserv de las partidas que no la tengan, por descripción. Devuelve cuántas."""
    mapa = mapa_claves(db, empresa_id=pedimento.empresa_id)
    n = 0
    for p in pedimento.partidas:
        if p.clave_prodserv:
            continue
        c = mapa.get(normalizar(p.descripcion))
        if c is not None:
            p.clave_prodserv = c.clave_prodserv
            if c.clave_unidad_sat and not p.clave_unidad_sat:
                p.clave_unidad_sat = c.clave_unidad_sat
            n += 1
    return n


def plantilla() -> bytes:
    return tabular.plantilla_xlsx(
        "Conceptos",
        COLUMNAS_PLANTILLA,
        ["ACUMULADORES", "26111700", "H87"],
        [
            "Una fila por concepto (descripción de la mercancía tal como viene en el pedimento).",
            "Clave SAT: 8 dígitos del catálogo c_ClaveProdServ del CFDI 4.0.",
            "Clave unidad (opcional): c_ClaveUnidad, p. ej. H87 pieza, PR par, KGM kilo.",
            "Si el concepto ya existe se actualiza su clave; el emparejamiento no distingue mayúsculas ni acentos.",
        ],
    )
