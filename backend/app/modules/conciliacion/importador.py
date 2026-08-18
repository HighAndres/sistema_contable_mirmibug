"""Importa un estado de cuenta desde Excel (.xlsx) o CSV con detección flexible
de columnas. No hay un layout único entre bancos, así que se buscan encabezados
por sinónimos y se aceptan dos formas de expresar el monto:

    - columnas separadas de cargo/retiro y abono/depósito, o
    - una sola columna de importe con signo (negativo = cargo).

Las filas sin fecha o sin monto se ignoran (encabezados repetidos, totales,
líneas en blanco). Devuelve filas normalizadas listas para persistir.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.utils.tabular import ArchivoTabularError, a_decimal as _decimal, a_fecha as _fecha, detectar_columnas, leer_tabla

SINONIMOS = {
    "fecha": ["fecha", "fecha operacion", "fecha de operacion", "fecha valor", "fecha mov", "date", "fec"],
    "concepto": ["concepto", "descripcion", "description", "detalle", "movimiento", "leyenda", "referencia ampliada"],
    "referencia": ["referencia", "ref", "folio", "numero de referencia", "no. referencia", "clave de rastreo"],
    "cargo": ["cargo", "cargos", "retiro", "retiros", "debito", "debe", "salida", "egreso", "withdrawal", "debit"],
    "abono": ["abono", "abonos", "deposito", "depositos", "credito", "haber", "entrada", "ingreso", "deposit", "credit"],
    "saldo": ["saldo", "balance", "saldo final"],
    "importe": ["importe", "monto", "cantidad", "amount", "total"],
}


class ImportacionError(ArchivoTabularError):
    pass


@dataclass
class FilaBanco:
    fila: int
    fecha: date
    concepto: str
    referencia: str | None
    cargo: Decimal
    abono: Decimal
    saldo: Decimal | None

    @property
    def huella(self) -> str:
        base = f"{self.fecha.isoformat()}|{self.concepto.strip().upper()}|{(self.referencia or '').strip()}|{self.cargo}|{self.abono}|{self.saldo}|{self.fila}"
        return hashlib.sha1(base.encode("utf-8")).hexdigest()


def _detectar_columnas(encabezados: list[object]) -> dict[str, int]:
    return detectar_columnas(encabezados, SINONIMOS)


def _leer_tabla(contenido: bytes, nombre: str) -> list[list[object]]:
    try:
        return leer_tabla(contenido, nombre)
    except ArchivoTabularError as exc:
        raise ImportacionError(str(exc)) from exc


def importar_estado_cuenta(contenido: bytes, nombre_archivo: str) -> tuple[list[FilaBanco], dict[str, int], list[str]]:
    """Devuelve (filas, mapa de columnas detectado, advertencias)."""
    tabla = _leer_tabla(contenido, nombre_archivo)
    tabla = [r for r in tabla if r and any(c not in (None, "") for c in r)]
    if not tabla:
        raise ImportacionError("El archivo está vacío")

    # El encabezado puede no estar en la primera fila (logos, título del banco...):
    # se busca la primera fila que contenga al menos fecha y (importe o cargo/abono).
    idx_encabezado, mapa = None, {}
    for i, fila in enumerate(tabla[:30]):
        m = _detectar_columnas(fila)
        if "fecha" in m and ("importe" in m or "cargo" in m or "abono" in m):
            idx_encabezado, mapa = i, m
            break
    if idx_encabezado is None:
        raise ImportacionError(
            "No se encontró un encabezado con columnas de fecha y monto (cargo/abono o importe). "
            "Columnas aceptadas: fecha, concepto/descripción, referencia, cargo/retiro, abono/depósito, importe, saldo."
        )

    advertencias: list[str] = []
    filas: list[FilaBanco] = []
    omitidas = 0
    for n, fila in enumerate(tabla[idx_encabezado + 1 :], start=idx_encabezado + 2):
        get = lambda campo: fila[mapa[campo]] if campo in mapa and mapa[campo] < len(fila) else None  # noqa: E731
        fecha = _fecha(get("fecha"))
        if fecha is None:
            omitidas += 1
            continue
        cargo = _decimal(get("cargo")) or Decimal("0")
        abono = _decimal(get("abono")) or Decimal("0")
        if "importe" in mapa and "cargo" not in mapa and "abono" not in mapa:
            imp = _decimal(get("importe"))
            if imp is None:
                omitidas += 1
                continue
            cargo, abono = (abs(imp), Decimal("0")) if imp < 0 else (Decimal("0"), imp)
        cargo, abono = abs(cargo).quantize(Decimal("0.01")), abs(abono).quantize(Decimal("0.01"))
        if cargo == 0 and abono == 0:
            omitidas += 1
            continue
        concepto = str(get("concepto") or "").strip() or "(sin concepto)"
        referencia = str(get("referencia") or "").strip() or None
        saldo = _decimal(get("saldo"))
        filas.append(FilaBanco(fila=n, fecha=fecha, concepto=concepto[:300], referencia=referencia[:80] if referencia else None, cargo=cargo, abono=abono, saldo=saldo.quantize(Decimal("0.01")) if saldo is not None else None))

    if not filas:
        raise ImportacionError("No se encontró ningún movimiento con fecha y monto válidos")
    if omitidas:
        advertencias.append(f"Se omitieron {omitidas} filas sin fecha o sin monto (encabezados, totales o líneas vacías).")
    if "concepto" not in mapa:
        advertencias.append("No se detectó columna de concepto/descripción; los movimientos quedaron sin concepto.")
    return filas, mapa, advertencias
