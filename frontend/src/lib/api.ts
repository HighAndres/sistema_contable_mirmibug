// Cliente HTTP autenticado: adjunta el Bearer token y, si hay una empresa
// activa seleccionada, el header X-Empresa-Id que el backend usa para
// resolver el rol/permisos del usuario en esa empresa (RBAC multi-tenant).

import { getAccessToken, tryRefresh } from "@/lib/auth-client";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000/api/v1";
const EMPRESA_ACTIVA_KEY = "nubinox_empresa_activa_id";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export function getEmpresaActivaId(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(EMPRESA_ACTIVA_KEY);
}

export function setEmpresaActivaId(empresaId: string) {
  window.localStorage.setItem(EMPRESA_ACTIVA_KEY, empresaId);
}

function parseErrorBody(body: unknown): string | null {
  if (body && typeof body === "object" && "detail" in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      return detail
        .map((d) => (d && typeof d === "object" && "msg" in d ? String((d as { msg: unknown }).msg) : String(d)))
        .join(", ");
    }
  }
  return null;
}

async function doFetch(path: string, init: RequestInit, token: string | null): Promise<Response> {
  const empresaId = getEmpresaActivaId();
  // Con FormData (subida de archivos) el navegador fija el Content-Type con
  // el boundary multipart; forzarlo a JSON rompería la petición.
  const esFormData = typeof FormData !== "undefined" && init.body instanceof FormData;
  const headers: Record<string, string> = {
    ...(esFormData ? {} : { "Content-Type": "application/json" }),
    ...(init.headers as Record<string, string> | undefined),
  };
  if (token) headers.Authorization = `Bearer ${token}`;
  if (empresaId) headers["X-Empresa-Id"] = empresaId;

  return fetch(`${API}${path}`, { ...init, headers });
}

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  let token = getAccessToken();
  if (!token) throw new ApiError(401, "No autenticado");

  let res = await doFetch(path, init, token);

  if (res.status === 401) {
    const refreshed = await tryRefresh();
    if (refreshed) {
      token = getAccessToken();
      res = await doFetch(path, init, token);
    }
    if (res.status === 401) {
      throw new ApiError(401, "Sesión expirada, inicia sesión de nuevo");
    }
  }

  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = parseErrorBody(await res.json()) || detail;
    } catch {
      /* sin cuerpo JSON */
    }
    throw new ApiError(res.status, detail);
  }

  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

/** Descarga un archivo binario autenticado (PDF, etc.) y dispara el guardado en el navegador. */
export async function apiDownload(path: string, nombreArchivo: string): Promise<void> {
  const token = getAccessToken();
  if (!token) throw new ApiError(401, "No autenticado");
  let res = await doFetch(path, { method: "GET" }, token);
  if (res.status === 401 && (await tryRefresh())) {
    res = await doFetch(path, { method: "GET" }, getAccessToken());
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = parseErrorBody(await res.json()) || detail;
    } catch {
      /* sin cuerpo JSON */
    }
    throw new ApiError(res.status, detail);
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = nombreArchivo;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
