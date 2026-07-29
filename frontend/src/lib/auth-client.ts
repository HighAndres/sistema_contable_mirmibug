// Cliente de autenticación (navegador). Guarda los JWT en localStorage.

import type { TokenPair, Usuario } from "@/lib/types";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000/api/v1";
const ACCESS_KEY = "nubinox_access_token";
const REFRESH_KEY = "nubinox_refresh_token";

export function getAccessToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(ACCESS_KEY);
}

function storeTokens(t: TokenPair) {
  window.localStorage.setItem(ACCESS_KEY, t.access_token);
  window.localStorage.setItem(REFRESH_KEY, t.refresh_token);
}

export function clearTokens() {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(ACCESS_KEY);
  window.localStorage.removeItem(REFRESH_KEY);
}

async function readError(res: Response): Promise<string> {
  try {
    const body = await res.json();
    if (typeof body?.detail === "string") return body.detail;
  } catch {
    /* sin cuerpo */
  }
  return res.statusText;
}

/** Login con email + contraseña (OAuth2 password flow: form-urlencoded). */
export async function login(email: string, password: string): Promise<void> {
  const form = new URLSearchParams({ username: email, password });
  const res = await fetch(`${API}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: form,
  });
  if (!res.ok) throw new Error(await readError(res));
  storeTokens(await res.json());
}

export async function register(email: string, password: string, nombre_completo?: string): Promise<void> {
  const res = await fetch(`${API}/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password, nombre_completo }),
  });
  if (!res.ok) throw new Error(await readError(res));
}

/** Siempre resuelve con un mensaje genérico: no revela si el correo existe. */
export async function forgotPassword(email: string): Promise<string> {
  const res = await fetch(`${API}/auth/forgot-password`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email }),
  });
  const body = await res.json();
  return body.detail as string;
}

export async function resetPassword(token: string, newPassword: string): Promise<void> {
  const res = await fetch(`${API}/auth/reset-password`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ token, new_password: newPassword }),
  });
  if (!res.ok) throw new Error(await readError(res));
}

export async function tryRefresh(): Promise<boolean> {
  const refresh_token = window.localStorage.getItem(REFRESH_KEY);
  if (!refresh_token) return false;
  const res = await fetch(`${API}/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token }),
  });
  if (!res.ok) {
    clearTokens();
    return false;
  }
  storeTokens(await res.json());
  return true;
}

/** Devuelve el usuario actual, intentando refrescar el token si expiró. */
export async function me(): Promise<Usuario | null> {
  const token = getAccessToken();
  if (!token) return null;
  let res = await fetch(`${API}/auth/me`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (res.status === 401 && (await tryRefresh())) {
    res = await fetch(`${API}/auth/me`, {
      headers: { Authorization: `Bearer ${getAccessToken()}` },
    });
  }
  if (!res.ok) {
    clearTokens();
    return null;
  }
  return res.json() as Promise<Usuario>;
}
