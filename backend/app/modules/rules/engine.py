"""Motor de validación fiscal: corre un conjunto fijo de reglas sobre CFDIs.

Simplificado respecto a un motor real (iAudita anuncia 428 validaciones):
aquí hay 3 reglas representativas, suficientes para que la demo muestre
alertas creíbles en el dashboard y la lista de CFDI.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

from app.modules.cfdi.models import Cfdi

# Lista mock de RFCs "EFOS" (empresas que facturan operaciones simuladas) para
# la demo — no corresponde a la lista real del SAT (art. 69-B).
RFCS_EFOS_MOCK: set[str] = {
    "EFO900101AAA",
    "EFO910202BBB",
    "EFO920303CCC",
}

TOLERANCIA_CUADRE = Decimal("1.00")
DIAS_LIMITE_COMPLEMENTO_PAGO = 30


def evaluar_cfdi(cfdi: Cfdi, *, hoy: date | None = None) -> list[tuple[str, str, str]]:
    """Devuelve una lista de (regla_codigo, severidad, detalle) para un CFDI."""
    hoy = hoy or date.today()
    alertas: list[tuple[str, str, str]] = []

    rfc_sospechoso = cfdi.rfc_emisor if cfdi.direccion == "recibido" else cfdi.rfc_receptor
    if rfc_sospechoso in RFCS_EFOS_MOCK:
        alertas.append((
            "efos_detectado",
            "alta",
            f"El RFC {rfc_sospechoso} aparece en la lista de posibles EFOS (art. 69-B, simulada).",
        ))

    suma_conceptos = sum((Decimal(str(c.importe)) for c in cfdi.conceptos), Decimal("0"))
    if cfdi.conceptos and abs(suma_conceptos - Decimal(str(cfdi.subtotal))) > TOLERANCIA_CUADRE:
        alertas.append((
            "descuadre_subtotal",
            "media",
            f"La suma de conceptos (${suma_conceptos:,.2f}) no coincide con el subtotal (${cfdi.subtotal:,.2f}).",
        ))

    dias_transcurridos = (hoy - cfdi.fecha).days
    if (
        cfdi.tipo in ("ingreso", "egreso")
        and cfdi.forma_pago_codigo == "99"
        and dias_transcurridos > DIAS_LIMITE_COMPLEMENTO_PAGO
        and cfdi.estatus == "vigente"
    ):
        alertas.append((
            "complemento_pago_pendiente",
            "media",
            f"CFDI 'Por definir' forma de pago con {dias_transcurridos} días sin complemento de pago registrado.",
        ))

    return alertas
