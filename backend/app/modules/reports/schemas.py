from pydantic import BaseModel


class DashboardKPIs(BaseModel):
    ingresos_total: float
    egresos_total: float
    utilidad: float
    iva_por_pagar: float
    isr_estimado: float
    flujo_caja: float
    cfdis_vigentes: int
    cfdis_con_alertas: int
    alertas_altas: int
    alertas_medias: int
    alertas_bajas: int


class MesMonto(BaseModel):
    mes: str  # YYYY-MM
    ingresos: float
    egresos: float


class TopContraparte(BaseModel):
    rfc: str
    nombre: str
    monto_total: float
    num_cfdis: int
