/** Etiquetas de catálogos del SAT que se muestran en pantalla. Son catálogos
 * estables (anexo 20 / complemento de nómina 1.2); si el SAT agrega claves, lo
 * no mapeado se muestra tal cual con su código. */

/** c_UsoCFDI (los usos reales del anexo 20). */
export const USO_CFDI: Record<string, string> = {
  G01: "Adquisición de mercancías",
  G02: "Devoluciones, descuentos o bonificaciones",
  G03: "Gastos en general",
  I01: "Construcciones",
  I02: "Mobiliario y equipo de oficina",
  I03: "Equipo de transporte",
  I04: "Equipo de cómputo y accesorios",
  I05: "Dados, troqueles, moldes y herramental",
  I06: "Comunicaciones telefónicas",
  I07: "Comunicaciones satelitales",
  I08: "Otra maquinaria y equipo",
  D01: "Honorarios médicos y dentales",
  D02: "Gastos médicos por incapacidad",
  D03: "Gastos funerales",
  D04: "Donativos",
  D05: "Intereses reales de créditos hipotecarios",
  D06: "Aportaciones voluntarias al SAR",
  D07: "Primas de seguros de gastos médicos",
  D08: "Gastos de transportación escolar",
  D09: "Depósitos para el ahorro / planes de pensiones",
  D10: "Pagos por servicios educativos",
  S01: "Sin efectos fiscales",
  CP01: "Pagos",
  CN01: "Nómina",
  P01: "Por definir (versión 3.3)",
};

/** c_PeriodicidadPago del complemento de nómina 1.2. */
export const PERIODICIDAD_PAGO: Record<string, string> = {
  "01": "Diario",
  "02": "Semanal",
  "03": "Catorcenal",
  "04": "Quincenal",
  "05": "Mensual",
  "06": "Bimestral",
  "07": "Unidad de obra",
  "08": "Comisión",
  "09": "Precio alzado",
  "10": "Decenal",
  "99": "Otra periodicidad",
};

/** c_Estado (las 32 entidades; DIF era la clave vieja de la CDMX). */
export const ENTIDADES: Record<string, string> = {
  AGU: "Aguascalientes",
  BCN: "Baja California",
  BCS: "Baja California Sur",
  CAM: "Campeche",
  COA: "Coahuila",
  COL: "Colima",
  CHP: "Chiapas",
  CHH: "Chihuahua",
  CMX: "Ciudad de México",
  DIF: "Ciudad de México",
  DUR: "Durango",
  GUA: "Guanajuato",
  GRO: "Guerrero",
  HID: "Hidalgo",
  JAL: "Jalisco",
  MEX: "Estado de México",
  MIC: "Michoacán",
  MOR: "Morelos",
  NAY: "Nayarit",
  NLE: "Nuevo León",
  OAX: "Oaxaca",
  PUE: "Puebla",
  QUE: "Querétaro",
  ROO: "Quintana Roo",
  SLP: "San Luis Potosí",
  SIN: "Sinaloa",
  SON: "Sonora",
  TAB: "Tabasco",
  TAM: "Tamaulipas",
  TLA: "Tlaxcala",
  VER: "Veracruz",
  YUC: "Yucatán",
  ZAC: "Zacatecas",
};

export const GRUPO_NOMINA: Record<string, string> = {
  percepcion: "Percepciones",
  deduccion: "Deducciones",
  otro_pago: "Otros pagos",
};

export const usoCfdiEtiqueta = (codigo: string | null) => (codigo ? `${codigo} · ${USO_CFDI[codigo] ?? ""}`.replace(/ · $/, "") : "—");
export const entidadEtiqueta = (codigo: string | null) => (codigo ? (ENTIDADES[codigo] ?? codigo) : "—");
export const periodicidadEtiqueta = (codigo: string | null) => (codigo ? (PERIODICIDAD_PAGO[codigo] ?? codigo) : "—");
