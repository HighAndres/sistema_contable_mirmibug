"""Proveedores de CFDI para la bóveda: la interfaz que comparten la simulación
actual, la carga manual de XML y —en la siguiente etapa— la descarga masiva del
Web Service del SAT con la e.firma del contribuyente.

Así el resto del sistema (rules, impuestos, conciliación, dashboard) no cambia
cuando se conecte el SAT real: solo se agrega otro proveedor.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from app.modules.tenants.models import Empresa


@dataclass
class ResultadoSincronizacion:
    cfdis_nuevos: int
    alertas_generadas: int
    detalle: dict | None = None


class ProveedorCfdi(ABC):
    nombre: str

    @abstractmethod
    def sincronizar(self, db: Session, *, empresa: Empresa, desde: date | None, hasta: date | None) -> ResultadoSincronizacion: ...


class ProveedorMock(ProveedorCfdi):
    """Genera CFDIs simulados (demo)."""

    nombre = "mock"

    def sincronizar(self, db, *, empresa, desde=None, hasta=None):
        import random

        from app.modules.rules import crud as rules_crud
        from app.modules.sat.mock_generator import generar_cfdis_mock

        cantidad = random.randint(5, 15)
        nuevos = generar_cfdis_mock(db, empresa=empresa, cantidad=cantidad, dias_atras=30)
        alertas = rules_crud.evaluar_cfdis(db, nuevos)
        return ResultadoSincronizacion(cfdis_nuevos=len(nuevos), alertas_generadas=alertas)


class ProveedorWebServiceSat(ProveedorCfdi):
    """Descarga masiva del SAT (solicitud → verificación → paquetes ZIP) con la
    e.firma de la empresa. Pendiente: requiere custodiar el .cer/.key cifrados y
    la librería de firma. Cuando exista, entrega ZIPs a `carga_xml.cargar_archivos`."""

    nombre = "sat_ws"

    def sincronizar(self, db, *, empresa, desde=None, hasta=None):
        raise NotImplementedError(
            "La descarga masiva del SAT requiere cargar la e.firma (FIEL) de la empresa; "
            "mientras tanto usa la carga de XML/ZIP o la sincronización simulada."
        )


def obtener_proveedor(nombre: str = "mock") -> ProveedorCfdi:
    return {"mock": ProveedorMock, "sat_ws": ProveedorWebServiceSat}[nombre]()
