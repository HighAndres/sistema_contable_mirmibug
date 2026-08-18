from pydantic import BaseModel


class AlertaRegla(BaseModel):
    regla_codigo: str
    descripcion: str
    severidad: str
    cfdis: int


class CuentasPendientes(BaseModel):
    """Facturas PPD vigentes sin complemento de pago (por cobrar / por pagar)."""

    num_cfdis: int
    subtotal: float
    iva: float
    total: float


class DashboardKPIs(BaseModel):
    anio: int
    mes: int | None  # None = anual
    ingresos_total: float
    egresos_total: float
    utilidad: float
    # IVA del módulo impuestos (base flujo) para el periodo: > 0 a cargo, < 0 a favor.
    iva_saldo: float
    # ISR del módulo impuestos: pago provisional del mes (mensual) o acumulado del ejercicio (anual).
    isr_estimado: float
    isr_mecanica: str
    flujo_caja: float
    cuentas_por_cobrar: CuentasPendientes
    cuentas_por_pagar: CuentasPendientes
    cfdis_vigentes: int
    cfdis_con_alertas: int
    alertas_altas: int
    alertas_medias: int
    alertas_bajas: int
    alertas_por_regla: list[AlertaRegla]
    # Compatibilidad con la versión anterior del dashboard.
    iva_por_pagar: float


class MesMonto(BaseModel):
    mes: str  # YYYY-MM
    ingresos: float
    egresos: float


class TopContraparte(BaseModel):
    rfc: str
    nombre: str
    monto_total: float
    num_cfdis: int
