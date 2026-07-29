"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";

import { useAuth } from "@/components/auth-provider";
import { apiFetch, getEmpresaActivaId, setEmpresaActivaId } from "@/lib/api";
import type { MiEmpresa } from "@/lib/types";

interface EmpresaContextValue {
  empresas: MiEmpresa[];
  empresaActiva: MiEmpresa | null;
  loading: boolean;
  seleccionarEmpresa: (empresaId: string) => void;
  refresh: () => Promise<void>;
}

const EmpresaContext = createContext<EmpresaContextValue | null>(null);

export function EmpresaProvider({ children }: { children: React.ReactNode }) {
  const { user } = useAuth();
  const [empresas, setEmpresas] = useState<MiEmpresa[]>([]);
  const [empresaActivaId, setEmpresaActivaIdState] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const cargar = useCallback(async () => {
    setLoading(true);
    try {
      const lista = await apiFetch<MiEmpresa[]>("/tenants/empresas/mias");
      setEmpresas(lista);
      const guardada = getEmpresaActivaId();
      const activa = lista.find((m) => m.empresa.id === guardada) ?? lista[0];
      if (activa) {
        setEmpresaActivaId(activa.empresa.id);
        setEmpresaActivaIdState(activa.empresa.id);
      }
    } catch {
      setEmpresas([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (user) void cargar();
    else setLoading(false);
  }, [user, cargar]);

  const seleccionarEmpresa = useCallback((empresaId: string) => {
    setEmpresaActivaId(empresaId);
    setEmpresaActivaIdState(empresaId);
  }, []);

  const empresaActiva = empresas.find((m) => m.empresa.id === empresaActivaId) ?? null;

  return (
    <EmpresaContext.Provider value={{ empresas, empresaActiva, loading, seleccionarEmpresa, refresh: cargar }}>
      {children}
    </EmpresaContext.Provider>
  );
}

export function useEmpresa() {
  const ctx = useContext(EmpresaContext);
  if (!ctx) throw new Error("useEmpresa debe usarse dentro de <EmpresaProvider>");
  return ctx;
}
