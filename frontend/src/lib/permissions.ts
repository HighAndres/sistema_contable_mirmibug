/**
 * Permisos del sistema, espejo del catálogo del backend
 * (backend/scripts/seed_rbac.py). Se resuelven por empresa activa, no de
 * forma global al usuario (ver empresa-provider.tsx).
 *
 * La autorización real vive en el backend: esto solo decide qué se muestra.
 * Nunca es la única barrera — cada endpoint valida por su cuenta.
 */

export const PERM = {
  EMPRESAS_LEER: "empresas.leer",
  EMPRESAS_EDITAR: "empresas.editar",
  USUARIOS_LEER: "usuarios.leer",
  USUARIOS_INVITAR: "usuarios.invitar",
  CREDENCIALES_GESTIONAR: "credenciales.gestionar",
  SAT_SINCRONIZAR: "sat.sincronizar",
  CFDI_LEER: "cfdi.leer",
  REPORTES_LEER: "reportes.leer",
  INVENTARIO_LEER: "inventario.leer",
  INVENTARIO_AJUSTAR: "inventario.ajustar",
  BITACORA_LEER: "bitacora.leer",
} as const;

export type Permiso = (typeof PERM)[keyof typeof PERM];

/** ¿La lista de permisos de la empresa activa incluye este permiso? */
export function can(permisos: readonly string[] | undefined, permiso: Permiso): boolean {
  return permisos?.includes(permiso) ?? false;
}

/** ¿Tiene al menos uno? Lista vacía de permisos requeridos = sin restricción. */
export function canAny(permisos: readonly string[] | undefined, requeridos: readonly Permiso[]): boolean {
  if (requeridos.length === 0) return true;
  return requeridos.some((p) => can(permisos, p));
}
