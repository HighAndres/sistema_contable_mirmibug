"""Generador de CFDIs simulados (sin conexión real al SAT).

Se usa tanto desde el endpoint POST /sat/sincronizar (lotes pequeños, como si
fuera una sincronización incremental) como desde scripts/seed_demo.py (lote
grande, para poblar la demo de una sola vez). No depende de librerías externas
(Faker, etc.) — son listas fijas suficientes para verse realistas.
"""

from __future__ import annotations

import random
import uuid
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import Integer, cast, func, select
from sqlalchemy.orm import Session

from app.modules.cfdi.models import Cfdi, CfdiConcepto
from app.modules.rules.engine import RFCS_EFOS_MOCK
from app.modules.tenants.models import Empresa

IVA_TASA = Decimal("0.16")

CONTRAPARTES = [
    "Comercializadora del Bajío SA de CV",
    "Grupo Industrial Ferretero SA de CV",
    "Distribuidora Peninsular SA de CV",
    "Consultores Asociados del Norte SC",
    "Transportes y Logística Aguilar SA de CV",
    "Servicios Corporativos Meridiano SA de CV",
    "Materiales de Construcción Ríos SA de CV",
    "Tecnología y Soluciones Digitales SAPI de CV",
    "Comercializadora Textil Jalisco SA de CV",
    "Refaccionaria Industrial del Golfo SA de CV",
    "Papelería y Suministros Corporativos SA de CV",
    "Alimentos Procesados del Centro SA de CV",
]

# Un par de contrapartes "irregulares" para que el motor de reglas las marque.
CONTRAPARTES_EFOS = [
    ("EFO900101AAA", "Servicios Integrales Fantasma SA de CV"),
    ("EFO910202BBB", "Comercializadora Sin Sustancia SA de CV"),
]

CONCEPTOS_INGRESO = [
    ("Servicio de consultoría fiscal mensual", "E48"),
    ("Desarrollo de software a medida", "E48"),
    ("Venta de mercancía por mayoreo", "H87"),
    ("Renta de equipo de cómputo", "E48"),
    ("Servicio de mantenimiento preventivo", "E48"),
]

CONCEPTOS_EGRESO = [
    ("Compra de papelería y consumibles", "H87"),
    ("Pago de servicio de internet dedicado", "E48"),
    ("Compra de mobiliario de oficina", "H87"),
    ("Servicio de limpieza mensual", "E48"),
    ("Compra de combustible para flotilla", "LTR"),
]

FORMAS_PAGO = ["01", "03", "04", "28", "99"]
USOS_CFDI = ["G01", "G03", "P01", "S01"]

EMPLEADOS = [
    ("María Fernanda López Ruiz", "LORM850312MN1"),
    ("José Antonio Ramírez Soto", "RASJ790825KL4"),
    ("Ana Karen Torres Medina", "TOMA920417QW7"),
    ("Luis Enrique Hernández Paz", "HEPL880930RT2"),
    ("Daniela Castillo Ortega", "CAOD950206YU8"),
    ("Ricardo Mendoza Villa", "MEVR830714PL5"),
]


def _siguiente_folio(db: Session, *, empresa_id, direccion: str) -> int:
    """Consecutivo por empresa/dirección, continuando el máximo ya guardado."""
    maximo = db.scalar(
        select(func.max(cast(Cfdi.folio, Integer))).where(
            Cfdi.empresa_id == empresa_id, Cfdi.direccion == direccion, Cfdi.folio.op("~")("^[0-9]+$")
        )
    )
    return int(maximo or 0) + 1


def _rfc_moral_aleatorio(rng: random.Random) -> str:
    letras = "".join(rng.choices("ABCDEFGHIJKLMNOPQRSTUVWXYZ", k=3))
    fecha = f"{rng.randint(90, 99)}{rng.randint(1, 12):02d}{rng.randint(1, 28):02d}"
    homoclave = "".join(rng.choices("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", k=3))
    return f"{letras}{fecha}{homoclave}"


def _generar_conceptos(
    rng: random.Random, banco: list[tuple[str, str]], *, rango_precio: tuple[int, int] = (150, 8000)
) -> list[dict]:
    n = rng.randint(1, 3)
    conceptos = []
    for _ in range(n):
        descripcion, unidad = rng.choice(banco)
        cantidad = rng.randint(1, 20)
        valor_unitario = Decimal(str(rng.randint(*rango_precio)))
        importe = (Decimal(cantidad) * valor_unitario).quantize(Decimal("0.01"))
        conceptos.append(
            {
                "descripcion": descripcion,
                "cantidad": float(cantidad),
                "unidad_codigo": unidad,
                # Decimal hasta el final: CfdiConcepto.valor_unitario/importe
                # ya son columnas Decimal, no hay motivo para pasar por float.
                "valor_unitario": valor_unitario,
                "importe": importe,
            }
        )
    return conceptos


def generar_cfdis_mock(
    db: Session,
    *,
    empresa: Empresa,
    cantidad: int,
    dias_atras: int = 180,
    incluir_irregulares: bool = True,
    seed: int | None = None,
) -> list[Cfdi]:
    """Genera `cantidad` CFDIs simulados para `empresa` y los persiste. No corre el motor de reglas."""
    rng = random.Random(seed)
    hoy = date.today()
    creados: list[Cfdi] = []
    folios = {
        "emitido": _siguiente_folio(db, empresa_id=empresa.id, direccion="emitido"),
        "recibido": _siguiente_folio(db, empresa_id=empresa.id, direccion="recibido"),
    }

    for i in range(cantidad):
        # El tipo se deriva de la dirección (no son independientes): un CFDI
        # "ingreso" siempre lo emite la empresa (es su venta) y un "egreso"
        # siempre lo recibe (es su gasto/compra) — así reports.crud puede
        # sumar por tipo sin tener que cruzar también por dirección. La nómina
        # la emite la empresa a sus empleados (sin IVA).
        direccion = rng.choices(["emitido", "recibido"], weights=[60, 40])[0]
        if direccion == "emitido":
            tipo = rng.choices(["ingreso", "pago", "nomina"], weights=[75, 13, 12])[0]
        else:
            tipo = rng.choices(["egreso", "pago"], weights=[85, 15])[0]
        fecha = hoy - timedelta(days=rng.randint(0, dias_atras))

        if tipo == "nomina":
            nombre_emp, rfc_emp = rng.choice(EMPLEADOS)
            # Quincena: la fecha cae en día 15 o último de mes.
            fecha = fecha.replace(day=15) if fecha.day <= 15 else (fecha.replace(day=28))
            sueldo = Decimal(str(rng.choice([6500, 8200, 9800, 12500, 15000, 18500])))
            cfdi = Cfdi(
                empresa_id=empresa.id,
                uuid_fiscal=str(uuid.uuid4()).upper(),
                version="4.0",
                serie="N",
                folio=str(folios["emitido"]),
                tipo="nomina",
                direccion="emitido",
                rfc_emisor=empresa.rfc,
                nombre_emisor=empresa.razon_social,
                rfc_receptor=rfc_emp,
                nombre_receptor=nombre_emp,
                forma_pago_codigo="99",
                metodo_pago_codigo=None,
                uso_cfdi_codigo="CN01",
                subtotal=sueldo,
                iva=Decimal("0"),
                total=sueldo,
                fecha=fecha,
                estatus="vigente",
            )
            cfdi.conceptos = [
                CfdiConcepto(
                    descripcion="Pago de nómina quincenal", cantidad=1.0, unidad_codigo="ACT",
                    valor_unitario=sueldo, importe=sueldo,
                )
            ]
            folios["emitido"] += 1
            db.add(cfdi)
            creados.append(cfdi)
            continue

        usar_efos = incluir_irregulares and rng.random() < 0.04
        if usar_efos:
            contraparte_rfc, contraparte_nombre = rng.choice(CONTRAPARTES_EFOS)
        else:
            contraparte_rfc, contraparte_nombre = _rfc_moral_aleatorio(rng), rng.choice(CONTRAPARTES)

        if direccion == "emitido":
            rfc_emisor, nombre_emisor = empresa.rfc, empresa.razon_social
            rfc_receptor, nombre_receptor = contraparte_rfc, contraparte_nombre
            banco_conceptos = CONCEPTOS_INGRESO
            # Precio de venta con margen sobre el de compra, para que la
            # empresa demo se vea rentable (más realista para una demo).
            rango_precio = (300, 9500)
        else:
            rfc_emisor, nombre_emisor = contraparte_rfc, contraparte_nombre
            rfc_receptor, nombre_receptor = empresa.rfc, empresa.razon_social
            banco_conceptos = CONCEPTOS_EGRESO
            rango_precio = (150, 6000)

        conceptos_data = _generar_conceptos(rng, banco_conceptos, rango_precio=rango_precio)
        subtotal = sum((c["importe"] for c in conceptos_data), Decimal("0"))
        iva = (subtotal * IVA_TASA).quantize(Decimal("0.01"))
        total = subtotal + iva

        r_est = rng.random()
        estatus = "cancelado" if r_est < 0.03 else ("en_proceso" if r_est < 0.045 else "vigente")

        if tipo == "pago":
            forma_pago, metodo_pago = rng.choice(["01", "03", "04", "28"]), None
        else:
            forma_pago = rng.choice(FORMAS_PAGO)
            # "99 Por definir" => se pagará después (PPD); lo demás en una sola exhibición.
            metodo_pago = "PPD" if forma_pago == "99" else "PUE"

        cfdi = Cfdi(
            empresa_id=empresa.id,
            uuid_fiscal=str(uuid.uuid4()).upper(),
            version="4.0",
            serie=("A" if direccion == "emitido" else rng.choice(["F", "FA", "B", None])) if tipo != "pago" else "P",
            folio=str(folios[direccion]),
            tipo=tipo,
            direccion=direccion,
            rfc_emisor=rfc_emisor,
            nombre_emisor=nombre_emisor,
            rfc_receptor=rfc_receptor,
            nombre_receptor=nombre_receptor,
            forma_pago_codigo=forma_pago,
            metodo_pago_codigo=metodo_pago,
            uso_cfdi_codigo=("CP01" if tipo == "pago" else rng.choice(USOS_CFDI)),
            subtotal=subtotal,
            iva=iva,
            total=total,
            fecha=fecha,
            estatus=estatus,
        )
        cfdi.conceptos = [CfdiConcepto(**data) for data in conceptos_data]
        folios[direccion] += 1
        db.add(cfdi)
        creados.append(cfdi)

    db.commit()
    for cfdi in creados:
        db.refresh(cfdi)
    return creados
