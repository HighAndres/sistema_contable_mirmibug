"""Impuesto Sobre Nóminas (ISN): impuesto ESTATAL sobre las erogaciones por
remuneraciones al trabajo personal subordinado.

La base se arma con los recibos de nómina de la bóveda, agrupados por la clave
de entidad federativa del complemento (ClaveEntFed), y se le aplica la tasa de
esa entidad. Como el ISN se causa sobre lo efectivamente pagado, el periodo se
determina por la fecha de pago del complemento (si no viene, por la fecha de
emisión del CFDI).

Las tasas viven aquí igual que los regímenes en `regimenes.py`: una tabla en
código que el despacho ajusta cuando cambia una ley estatal. Las de 2026 son
REFERENCIALES: las fuentes públicas no coinciden en todas las entidades (hay
sobretasas, tarifas progresivas y reformas recientes), así que hay que validar
la tasa de cada entidad donde el cliente tenga nómina contra la ley de hacienda
estatal o la lámina de referencia del despacho antes de usarla para declarar.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import extract, func, select
from sqlalchemy.orm import Session

from app.modules.cfdi.models import Cfdi, CfdiNomina

# Claves del catálogo c_Estado del SAT (las que usa ClaveEntFed en el
# complemento de nómina) → nombre y tasa de ISN 2026.
# "DIF" era la clave de la Ciudad de México antes de "CMX"; se normaliza.
ENTIDADES: dict[str, str] = {
    "AGU": "Aguascalientes",
    "BCN": "Baja California",
    "BCS": "Baja California Sur",
    "CAM": "Campeche",
    "COA": "Coahuila",
    "COL": "Colima",
    "CHP": "Chiapas",
    "CHH": "Chihuahua",
    "CMX": "Ciudad de México",
    "DUR": "Durango",
    "GUA": "Guanajuato",
    "GRO": "Guerrero",
    "HID": "Hidalgo",
    "JAL": "Jalisco",
    "MEX": "Estado de México",
    "MIC": "Michoacán",
    "MOR": "Morelos",
    "NAY": "Nayarit",
    "NLE": "Nuevo León",
    "OAX": "Oaxaca",
    "PUE": "Puebla",
    "QUE": "Querétaro",
    "ROO": "Quintana Roo",
    "SLP": "San Luis Potosí",
    "SIN": "Sinaloa",
    "SON": "Sonora",
    "TAB": "Tabasco",
    "TAM": "Tamaulipas",
    "TLA": "Tlaxcala",
    "VER": "Veracruz",
    "YUC": "Yucatán",
    "ZAC": "Zacatecas",
}

# Tasas 2026 (referenciales — ver el docstring del módulo). Donde la ley marca
# tarifa progresiva o sobretasas se anota la tasa típica/efectiva.
TASAS_ISN: dict[str, Decimal] = {
    "AGU": Decimal("0.025"),
    "BCN": Decimal("0.0425"),  # 1.80% base + sobretasas (efectiva)
    "BCS": Decimal("0.03"),
    "CAM": Decimal("0.03"),
    "COA": Decimal("0.02"),
    "COL": Decimal("0.02"),
    "CHP": Decimal("0.02"),
    "CHH": Decimal("0.04"),
    "CMX": Decimal("0.04"),
    "DUR": Decimal("0.03"),
    "GUA": Decimal("0.03"),
    "GRO": Decimal("0.03"),
    "HID": Decimal("0.03"),
    "JAL": Decimal("0.03"),
    "MEX": Decimal("0.03"),
    "MIC": Decimal("0.03"),
    "MOR": Decimal("0.03"),
    "NAY": Decimal("0.03"),
    "NLE": Decimal("0.03"),
    "OAX": Decimal("0.03"),
    "PUE": Decimal("0.03"),
    "QUE": Decimal("0.03"),
    "ROO": Decimal("0.04"),
    "SLP": Decimal("0.03"),
    "SIN": Decimal("0.027"),  # tarifa progresiva 2.4%–3% (tasa media)
    "SON": Decimal("0.03"),
    "TAB": Decimal("0.03"),
    "TAM": Decimal("0.03"),
    "TLA": Decimal("0.03"),
    "VER": Decimal("0.03"),
    "YUC": Decimal("0.0375"),
    "ZAC": Decimal("0.035"),
}


@dataclass
class FilaIsn:
    entidad_codigo: str | None  # None = recibos sin ClaveEntFed en el complemento
    entidad_nombre: str
    tasa: Decimal | None
    recibos: int
    percepciones: Decimal
    deducciones: Decimal
    otros_pagos: Decimal
    base: Decimal
    isn: Decimal


@dataclass
class ResultadoIsn:
    filas: list[FilaIsn]
    total_base: Decimal
    total_isn: Decimal
    advertencias: list[str]


def _normalizar_entidad(clave: str | None) -> str | None:
    if not clave:
        return None
    clave = clave.strip().upper()
    return "CMX" if clave == "DIF" else clave


def isn_periodo(db: Session, *, empresa_id: uuid.UUID, anio: int, mes: int | None) -> ResultadoIsn:
    """ISN del periodo por entidad federativa. La base es el total de
    percepciones (gravadas + exentas) de los recibos vigentes pagados en el
    periodo; las leyes estatales afinan qué conceptos entran, así que es una
    previa para comparar, no la declaración."""
    fecha_efectiva = func.coalesce(CfdiNomina.fecha_pago, Cfdi.fecha)
    stmt = (
        select(
            CfdiNomina.clave_ent_fed,
            func.count().label("recibos"),
            func.coalesce(func.sum(CfdiNomina.total_percepciones), 0),
            func.coalesce(func.sum(CfdiNomina.total_deducciones), 0),
            func.coalesce(func.sum(CfdiNomina.total_otros_pagos), 0),
        )
        .join(Cfdi, Cfdi.id == CfdiNomina.cfdi_id)
        .where(
            Cfdi.empresa_id == empresa_id,
            Cfdi.tipo == "nomina",
            Cfdi.estatus == "vigente",
            extract("year", fecha_efectiva) == anio,
        )
        .group_by(CfdiNomina.clave_ent_fed)
    )
    if mes:
        stmt = stmt.where(extract("month", fecha_efectiva) == mes)

    # Recibos de nómina sin complemento (p. ej. simulados): se reportan aparte
    # para que el total de la pestaña de nómina y el del ISN cuadren a la vista.
    stmt_sin = select(func.count(), func.coalesce(func.sum(Cfdi.total), 0)).where(
        Cfdi.empresa_id == empresa_id,
        Cfdi.tipo == "nomina",
        Cfdi.estatus == "vigente",
        extract("year", Cfdi.fecha) == anio,
        ~select(CfdiNomina.id).where(CfdiNomina.cfdi_id == Cfdi.id).correlate(Cfdi).exists(),
    )
    if mes:
        stmt_sin = stmt_sin.where(extract("month", Cfdi.fecha) == mes)

    agrupado: dict[str | None, list[Decimal | int]] = {}
    for clave, recibos, perc, ded, otros in db.execute(stmt).all():
        clave = _normalizar_entidad(clave)
        fila = agrupado.setdefault(clave, [0, Decimal("0"), Decimal("0"), Decimal("0")])
        fila[0] += int(recibos)
        fila[1] += Decimal(perc)
        fila[2] += Decimal(ded)
        fila[3] += Decimal(otros)

    filas: list[FilaIsn] = []
    advertencias: list[str] = []
    for clave, (recibos, perc, ded, otros) in sorted(agrupado.items(), key=lambda kv: kv[0] or "ZZZ"):
        tasa = TASAS_ISN.get(clave) if clave else None
        base = perc
        if clave and clave not in ENTIDADES:
            advertencias.append(f"Clave de entidad desconocida en los recibos: {clave}. Revisa el complemento de nómina.")
        if clave is None:
            advertencias.append(f"{recibos} recibo(s) sin clave de entidad federativa en el complemento: no se les calcula ISN.")
        filas.append(
            FilaIsn(
                entidad_codigo=clave,
                entidad_nombre=ENTIDADES.get(clave, "Sin entidad federativa") if clave else "Sin entidad federativa",
                tasa=tasa,
                recibos=int(recibos),
                percepciones=perc,
                deducciones=ded,
                otros_pagos=otros,
                base=base,
                isn=(base * tasa).quantize(Decimal("0.01")) if tasa else Decimal("0"),
            )
        )

    sin_complemento, total_sin = db.execute(stmt_sin).one()
    if sin_complemento:
        advertencias.append(
            f"{sin_complemento} recibo(s) de nómina sin complemento 1.2 (total ${Decimal(total_sin):,.2f}): "
            "no entran al cálculo. Suelen ser CFDI simulados o XML incompletos."
        )

    return ResultadoIsn(
        filas=filas,
        total_base=sum((f.base for f in filas), Decimal("0")),
        total_isn=sum((f.isn for f in filas), Decimal("0")),
        advertencias=advertencias,
    )


def anios_con_nomina(db: Session, *, empresa_id: uuid.UUID) -> list[int]:
    filas = db.scalars(
        select(extract("year", Cfdi.fecha))
        .where(Cfdi.empresa_id == empresa_id, Cfdi.tipo == "nomina")
        .distinct()
        .order_by(extract("year", Cfdi.fecha).desc())
    ).all()
    return [int(a) for a in filas] or [date.today().year]
