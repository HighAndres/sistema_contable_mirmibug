const MXN = new Intl.NumberFormat("es-MX", { style: "currency", currency: "MXN", maximumFractionDigits: 0 });

export function formatMoney(value: number): string {
  return MXN.format(value);
}

export function formatDate(iso: string): string {
  // Una fecha sin hora ("2026-01-03") se interpretaría como UTC medianoche y en
  // México se mostraría el día anterior; se construye como fecha local.
  const soloFecha = /^\d{4}-\d{2}-\d{2}$/.test(iso);
  const fecha = soloFecha
    ? new Date(Number(iso.slice(0, 4)), Number(iso.slice(5, 7)) - 1, Number(iso.slice(8, 10)))
    : new Date(iso);
  return new Intl.DateTimeFormat("es-MX", { day: "2-digit", month: "short", year: "numeric" }).format(fecha);
}

export function formatMes(mes: string): string {
  const [year, month] = mes.split("-");
  const fecha = new Date(Number(year), Number(month) - 1, 1);
  return new Intl.DateTimeFormat("es-MX", { month: "short", year: "2-digit" }).format(fecha);
}

const MXN_DEC = new Intl.NumberFormat("es-MX", { style: "currency", currency: "MXN", minimumFractionDigits: 2, maximumFractionDigits: 2 });
const NUM = new Intl.NumberFormat("es-MX", { maximumFractionDigits: 3 });

/** Moneda con centavos (para costeos y facturas). */
export function formatMoney2(value: number): string {
  return MXN_DEC.format(value);
}

/** Precio unitario con hasta 6 decimales (los del CFDI). */
export function formatUnit(value: number, decimales = 6): string {
  return value.toLocaleString("es-MX", { minimumFractionDigits: 2, maximumFractionDigits: decimales });
}

export function formatNumber(value: number): string {
  return NUM.format(value);
}
