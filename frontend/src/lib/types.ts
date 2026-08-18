export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface Usuario {
  id: string;
  email: string;
  nombre_completo: string | null;
  is_active: boolean;
  is_superadmin: boolean;
}

export interface MiembroEmpresa {
  usuario_id: string;
  email: string;
  nombre_completo: string | null;
  rol: string;
  is_active: boolean;
}

export interface UsuarioAdmin {
  id: string;
  email: string;
  nombre_completo: string | null;
  is_active: boolean;
  is_superadmin: boolean;
  num_empresas: number;
  created_at: string;
}

export interface InvitarUsuarioResponse {
  email: string;
  rol: string;
  usuario_nuevo: boolean;
  password_temporal: string | null;
}

export interface BitacoraEntrada {
  id: string;
  usuario_email: string;
  accion: string;
  descripcion: string;
  entidad_tipo: string | null;
  entidad_id: string | null;
  created_at: string;
}

export interface Empresa {
  id: string;
  rfc: string;
  razon_social: string;
  regimen_fiscal_codigo: string | null;
  tipo_persona: "moral" | "fisica";
  coeficiente_utilidad: number | null;
  activo: boolean;
}

export interface MiEmpresa {
  empresa: Empresa;
  rol: string;
  permisos: string[];
}

export interface CredencialSat {
  empresa_id: string;
  tipo: string;
  estado: "pendiente" | "conectado";
  conectado_at: string | null;
}

export interface Catalogo {
  id: string;
  tipo: string;
  codigo: string;
  nombre: string;
  activo: boolean;
}

export interface CfdiConcepto {
  id: string;
  descripcion: string;
  cantidad: number;
  unidad_codigo: string | null;
  valor_unitario: number;
  importe: number;
}

export interface CfdiAlerta {
  id: string;
  regla_codigo: string;
  severidad: "baja" | "media" | "alta";
  detalle: string;
  created_at: string;
}

export type CfdiTipo = "ingreso" | "egreso" | "pago" | "nomina" | "nota_credito";
export type CfdiEstatus = "vigente" | "cancelado" | "en_proceso";

export interface Cfdi {
  id: string;
  uuid_fiscal: string;
  version: string | null;
  serie: string | null;
  folio: string | null;
  tipo: CfdiTipo;
  direccion: "emitido" | "recibido";
  rfc_emisor: string;
  nombre_emisor: string;
  rfc_receptor: string;
  nombre_receptor: string;
  forma_pago_codigo: string | null;
  metodo_pago_codigo: "PUE" | "PPD" | null;
  uso_cfdi_codigo: string | null;
  subtotal: number;
  iva: number;
  total: number;
  fecha: string;
  estatus: CfdiEstatus;
  tipo_comprobante: string | null;
  origen: "mock" | "xml" | "descarga";
  iva_retenido: number;
  isr_retenido: number;
}

export interface PagoDocto {
  cfdi_pago_id: string;
  uuid_pago: string;
  uuid_relacionado: string;
  num_parcialidad: number | null;
  imp_saldo_anterior: number | null;
  imp_pagado: number;
  imp_saldo_insoluto: number | null;
  iva_pagado: number;
  fecha_pago: string | null;
  forma_pago_codigo: string | null;
}

export interface CargaXmlResponse {
  nuevos: number;
  duplicados: number;
  ajenos: number;
  alertas: number;
  errores: { archivo: string; error: string }[];
}

export interface CfdiResumenTipo {
  cantidad: number;
  cancelados: number;
  ppd: number;
  subtotal: number;
  iva: number;
  total: number;
}

export interface CfdiResumen {
  ingreso: CfdiResumenTipo;
  egreso: CfdiResumenTipo;
  pago: CfdiResumenTipo;
  nomina: CfdiResumenTipo;
  nota_credito: CfdiResumenTipo;
  anios: number[];
}

export interface CfdiDetalle extends Cfdi {
  conceptos: CfdiConcepto[];
  alertas: CfdiAlerta[];
  pagos_recibidos: PagoDocto[];
  saldo_pendiente: number | null;
  pagos_relacionados: PagoDocto[];
  tiene_xml: boolean;
}

export interface CfdiPage {
  items: Cfdi[];
  total: number;
  limit: number;
  offset: number;
}

export interface AlertaRegla {
  regla_codigo: string;
  descripcion: string;
  severidad: "alta" | "media" | "baja";
  cfdis: number;
}

export interface CuentasPendientes {
  num_cfdis: number;
  subtotal: number;
  iva: number;
  total: number;
}

export interface DashboardKPIs {
  anio: number;
  mes: number | null;
  ingresos_total: number;
  egresos_total: number;
  utilidad: number;
  iva_saldo: number;
  iva_por_pagar: number;
  isr_estimado: number;
  isr_mecanica: string;
  flujo_caja: number;
  cuentas_por_cobrar: CuentasPendientes;
  cuentas_por_pagar: CuentasPendientes;
  cfdis_vigentes: number;
  cfdis_con_alertas: number;
  alertas_altas: number;
  alertas_medias: number;
  alertas_bajas: number;
  alertas_por_regla: AlertaRegla[];
}

export interface VigenciaCertificado {
  tipo: "fiel" | "csd";
  numero_serie: string | null;
  vence: string | null;
  dias_restantes: number | null;
  estado: "sin_datos" | "vencida" | "por_vencer" | "vigente";
}

export interface Vigencias {
  conectado: boolean;
  fiel: VigenciaCertificado;
  csd: VigenciaCertificado;
}

export interface MesMonto {
  mes: string;
  ingresos: number;
  egresos: number;
}

export interface TopContraparte {
  rfc: string;
  nombre: string;
  monto_total: number;
  num_cfdis: number;
}

export interface Almacen {
  id: string;
  nombre: string;
  codigo: string;
  activo: boolean;
}

export interface Producto {
  id: string;
  sku: string;
  nombre: string;
  tipo: "producto" | "servicio";
  categoria: string | null;
  unidad_codigo: string | null;
  costo_unitario: number;
  atributos: Record<string, unknown> | null;
  clave_prodserv?: string | null;
  activo: boolean;
}

export interface StockItem {
  producto_id: string;
  sku: string;
  nombre_producto: string;
  categoria: string | null;
  almacen_id: string;
  codigo_almacen: string;
  disponible: number;
}

export interface Movimiento {
  id: string;
  tipo: "entrada" | "salida" | "ajuste";
  cantidad: number;
  costo_unitario: number | null;
  referencia: string | null;
  nota: string | null;
  fecha: string;
  sku: string;
  nombre_producto: string;
  codigo_almacen: string;
}

// ---------- Pedimentos de importación ----------

export type MetodoProrrateo = "partes_iguales" | "valor_aduana" | "cantidad" | "peso";

export interface GastoAdicional {
  concepto: string;
  monto: number;
}

export interface PartidaCosteo {
  dta_asignado: number;
  dta_pza: number;
  igi_pza: number;
  gastos_asignados: number;
  gastos_pza: number;
  utilidad_asignada: number;
  utilidad_pza: number;
  costo_unitario: number;
  precio_unitario_venta: number;
  subtotal: number;
  iva_16: number;
  total: number;
  dif_iva: number;
}

export interface PedimentoPartida {
  id: string;
  secuencia: number;
  fraccion: string;
  nico: string | null;
  descripcion: string;
  pais_origen: string | null;
  cantidad_umc: number;
  umc_clave: string;
  umc_descripcion: string | null;
  cantidad_umt: number | null;
  umt_clave: string | null;
  precio_unitario: number;
  valor_aduana: number;
  valor_comercial: number;
  valor_usd: number;
  igi: number;
  iva: number;
  tasa_igi: number | null;
  tasa_iva: number | null;
  clave_prodserv: string | null;
  clave_unidad_sat: string | null;
  producto_id: string | null;
  producto_sku: string | null;
  costeo: PartidaCosteo;
}

export interface CosteoResumen {
  dta: number;
  gastos_adicionales: number;
  utilidad: number;
  igi_total: number;
  iva_importacion_total: number;
  costo_total: number;
  subtotal_venta: number;
  iva_venta: number;
  total_venta: number;
  dif_iva_total: number;
}

export interface PedimentoResumen {
  id: string;
  numero_completo: string;
  numero: string;
  patente: string;
  aduana: string;
  clave_pedimento: string | null;
  referencia: string | null;
  fecha_pago: string | null;
  tipo_cambio: number;
  proveedor_nombre: string | null;
  num_partidas: number;
  valor_aduana_total: number;
  dta: number;
  igi_total: number;
  iva_total: number;
  estatus: "borrador" | "aplicado";
  origen: "m3" | "manual";
  created_at: string;
}

export interface PedimentoDetalle extends PedimentoResumen {
  tipo_operacion: string | null;
  rfc_importador: string | null;
  fecha_entrada: string | null;
  peso_bruto: number | null;
  incoterm: string | null;
  proveedor_id_fiscal: string | null;
  contenedores: string[] | null;
  guias: string[] | null;
  otras_contribuciones: Record<string, string> | null;
  gastos_adicionales: GastoAdicional[];
  utilidad: number;
  metodo_prorrateo: MetodoProrrateo;
  aplicado_almacen_id: string | null;
  archivo_nombre: string | null;
  notas: string | null;
  valor_usd_total: number;
  resumen: CosteoResumen;
  partidas: PedimentoPartida[];
}

export interface ImportarM3Response {
  pedimento: PedimentoDetalle;
  advertencias: string[];
}

export interface AplicarInventarioResponse {
  pedimento_id: string;
  movimientos_creados: number;
  productos_creados: number;
  costo_total: number;
}

// ---------- Impuestos ----------

export interface DesgloseIva {
  concepto: string;
  num_cfdis: number;
  base: number;
  iva: number;
}

export interface IvaPeriodo {
  anio: number;
  mes: number | null;
  trasladado_cobrado: number;
  acreditable_pagado: number;
  saldo: number;
  trasladado_ppd_pendiente: number;
  acreditable_ppd_pendiente: number;
  emitidas: DesgloseIva[];
  recibidas: DesgloseIva[];
  anios_disponibles: number[];
}

export type MecanicaIsr = "pm_general" | "pm_resico" | "pf_resico" | "pf_actividad" | "no_aplica";

export interface MesIsr {
  mes: number;
  ingresos_mes: number;
  deducciones_mes: number;
  ingresos_acumulados: number;
  deducciones_acumuladas: number;
  base: number;
  tasa_aplicada: number | null;
  isr_acumulado: number;
  pagos_anteriores: number;
  isr_del_mes: number;
}

export interface IsrEjercicio {
  anio: number;
  hasta_mes: number;
  mecanica: MecanicaIsr;
  descripcion: string;
  tipo_persona: "moral" | "fisica";
  regimen_fiscal_codigo: string | null;
  coeficiente_utilidad: number | null;
  meses: MesIsr[];
  advertencias: string[];
  anios_disponibles: number[];
}

export interface ConfiguracionFiscal {
  rfc: string;
  razon_social: string;
  tipo_persona: "moral" | "fisica";
  regimen_fiscal_codigo: string | null;
  coeficiente_utilidad: number | null;
  mecanica_isr: MecanicaIsr;
}

// ---------- Conciliación ----------

export interface CuentaBancaria {
  id: string;
  banco: string;
  alias: string;
  numero: string | null;
  moneda: string;
  activo: boolean;
}

export type EstadoMovimientoBanco = "pendiente" | "conciliado" | "ignorado";

export interface MovimientoBanco {
  id: string;
  cuenta_id: string;
  cuenta_alias: string;
  fecha: string;
  concepto: string;
  referencia: string | null;
  cargo: number;
  abono: number;
  saldo: number | null;
  estado: EstadoMovimientoBanco;
  conciliado_por: "auto" | "manual" | null;
  nota: string | null;
  cfdi_id: string | null;
  cfdi_uuid: string | null;
  cfdi_nombre: string | null;
  cfdi_total: number | null;
  archivo_nombre: string | null;
  created_at: string;
}

export interface MovimientosBancoPage {
  items: MovimientoBanco[];
  total: number;
}

export interface ImportarBancoResponse {
  cuenta_id: string;
  importados: number;
  duplicados: number;
  columnas_detectadas: Record<string, number>;
  advertencias: string[];
  fecha_min: string | null;
  fecha_max: string | null;
}

export interface AutoConciliarResponse {
  revisados: number;
  conciliados: number;
  sin_coincidencia: number;
  ambiguos: number;
}

export interface CandidatoCfdi {
  cfdi_id: string;
  uuid_fiscal: string;
  tipo: string;
  direccion: string;
  fecha: string;
  nombre_contraparte: string;
  rfc_contraparte: string;
  total: number;
  diferencia: number;
  dias: number;
}

export interface Declaracion {
  anio: number;
  mes: number;
  ingresos_declarados: number | null;
  deducciones_declaradas: number | null;
  iva_declarado: number | null;
  isr_declarado: number | null;
  fecha_presentacion: string | null;
  numero_operacion: string | null;
  notas: string | null;
  capturada: boolean;
}

export interface ResumenConciliacion {
  anio: number;
  mes: number;
  sat: {
    ingresos_cobrados: number;
    egresos_pagados: number;
    ingresos_facturados: number;
    iva_saldo: number;
    isr_estimado: number;
    num_cfdis: number;
  };
  banco: {
    abonos: number;
    cargos: number;
    num_movimientos: number;
    abonos_conciliados: number;
    cargos_conciliados: number;
    pendientes: number;
    conciliados: number;
    ignorados: number;
    porcentaje_conciliado: number;
  };
  declarado: Declaracion;
  diferencias: {
    ingresos_sat_vs_banco: number;
    ingresos_sat_vs_declarado: number | null;
    iva_sat_vs_declarado: number | null;
    isr_sat_vs_declarado: number | null;
  };
  semaforo: "ok" | "revisar" | "sin_declaracion";
}

// ---------- Terceros (clientes / proveedores) ----------

export type TerceroTipo = "cliente" | "proveedor" | "ambos";

export interface Antiguedad {
  d0_30: number;
  d31_60: number;
  d61_90: number;
  d90_mas: number;
  total: number;
  num_cfdis: number;
}

export interface Tercero {
  id: string;
  rfc: string;
  nombre: string;
  tipo: TerceroTipo;
  regimen_fiscal_codigo: string | null;
  codigo_postal: string | null;
  uso_cfdi_default: string | null;
  email: string | null;
  telefono: string | null;
  contacto: string | null;
  dias_credito: number;
  limite_credito: number | null;
  notas: string | null;
  origen: "cfdi" | "manual" | "excel";
  activo: boolean;
  es_efos: boolean;
  created_at: string;
  num_cfdis: number;
  facturado_12m: number;
  saldo_pendiente: number;
  ultimo_cfdi: string | null;
}

export interface TerceroDetalle extends Tercero {
  por_cobrar: Antiguedad;
  por_pagar: Antiguedad;
  total_emitido: number;
  total_recibido: number;
}
