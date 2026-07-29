"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";

import * as auth from "@/lib/auth-client";
import type { Usuario } from "@/lib/types";

interface AuthContextValue {
  user: Usuario | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  refresh: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<Usuario | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    auth
      .me()
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setLoading(false));
  }, []);

  const doLogout = useCallback(() => {
    auth.clearTokens();
    setUser(null);
  }, []);

  const refreshUser = useCallback(async () => {
    try {
      setUser(await auth.me());
    } catch {
      setUser(null);
    }
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    await auth.login(email, password);
    setUser(await auth.me());
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, login, logout: doLogout, refresh: refreshUser }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth debe usarse dentro de <AuthProvider>");
  return ctx;
}
