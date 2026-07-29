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

export interface Cfdi {
  id: string;
  uuid_fiscal: string;
  tipo: "ingreso" | "egreso" | "pago" | "nomina";
  direccion: "emitido" | "recibido";
  rfc_emisor: string;
  nombre_emisor: string;
  rfc_receptor: string;
  nombre_receptor: string;
  forma_pago_codigo: string | null;
  uso_cfdi_codigo: string | null;
  subtotal: number;
  iva: number;
  total: number;
  fecha: string;
  estatus: "vigente" | "cancelado";
}

export interface CfdiDetalle extends Cfdi {
  conceptos: CfdiConcepto[];
  alertas: CfdiAlerta[];
}

export interface CfdiPage {
  items: Cfdi[];
  total: number;
  limit: number;
  offset: number;
}

export interface DashboardKPIs {
  ingresos_total: number;
  egresos_total: number;
  utilidad: number;
  iva_por_pagar: number;
  isr_estimado: number;
  flujo_caja: number;
  cfdis_vigentes: number;
  cfdis_con_alertas: number;
  alertas_altas: number;
  alertas_medias: number;
  alertas_bajas: number;
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
  referencia: string | null;
  nota: string | null;
  fecha: string;
  sku: string;
  nombre_producto: string;
  codigo_almacen: string;
}
