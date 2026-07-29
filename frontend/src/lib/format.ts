const MXN = new Intl.NumberFormat("es-MX", { style: "currency", currency: "MXN", maximumFractionDigits: 0 });

export function formatMoney(value: number): string {
  return MXN.format(value);
}

export function formatDate(iso: string): string {
  return new Intl.DateTimeFormat("es-MX", { day: "2-digit", month: "short", year: "numeric" }).format(
    new Date(iso),
  );
}

export function formatMes(mes: string): string {
  const [year, month] = mes.split("-");
  const fecha = new Date(Number(year), Number(month) - 1, 1);
  return new Intl.DateTimeFormat("es-MX", { month: "short", year: "2-digit" }).format(fecha);
}
