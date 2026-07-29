"use client";

import { useCallback, useEffect, useState } from "react";
import { Building2, CheckCircle2 } from "lucide-react";

import { useEmpresa } from "@/components/empresa-provider";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError, apiFetch } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { PERM, can } from "@/lib/permissions";
import type { CredencialSat } from "@/lib/types";

export default function EmpresasPage() {
  const { empresas, empresaActiva, seleccionarEmpresa, refresh } = useEmpresa();
  const [rfc, setRfc] = useState("");
  const [razonSocial, setRazonSocial] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [credencial, setCredencial] = useState<CredencialSat | null>(null);
  const [conectando, setConectando] = useState(false);

  const cargarCredencial = useCallback(async () => {
    if (!empresaActiva) return;
    try {
      setCredencial(await apiFetch<CredencialSat | null>("/credentials"));
    } catch {
      setCredencial(null);
    }
  }, [empresaActiva]);

  useEffect(() => {
    void cargarCredencial();
  }, [cargarCredencial]);

  async function crearEmpresa(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const nueva = await apiFetch<{ id: string }>("/tenants/empresas", {
        method: "POST",
        body: JSON.stringify({ rfc, razon_social: razonSocial }),
      });
      setRfc("");
      setRazonSocial("");
      await refresh();
      seleccionarEmpresa(nueva.id);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "No se pudo crear la empresa");
    } finally {
      setSubmitting(false);
    }
  }

  async function conectarSat() {
    setConectando(true);
    try {
      await apiFetch<CredencialSat>("/credentials/conectar", {
        method: "POST",
        body: JSON.stringify({ tipo: "ciec" }),
      });
      await cargarCredencial();
    } finally {
      setConectando(false);
    }
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Empresas</h1>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Tus empresas</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {empresas.map((m) => (
              <button
                key={m.empresa.id}
                onClick={() => seleccionarEmpresa(m.empresa.id)}
                className={`flex w-full items-center justify-between rounded-md border p-3 text-left text-sm transition-colors ${
                  empresaActiva?.empresa.id === m.empresa.id ? "border-primary bg-accent" : "hover:bg-accent"
                }`}
              >
                <div className="flex items-center gap-2">
                  <Building2 className="h-4 w-4 text-muted-foreground" />
                  <div>
                    <p className="font-medium">{m.empresa.razon_social}</p>
                    <p className="font-mono text-xs text-muted-foreground">{m.empresa.rfc}</p>
                  </div>
                </div>
                <Badge variant="secondary">{m.rol}</Badge>
              </button>
            ))}
            {empresas.length === 0 && (
              <p className="text-sm text-muted-foreground">Aún no perteneces a ninguna empresa.</p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Crear nueva empresa</CardTitle>
          </CardHeader>
          <CardContent>
            <form onSubmit={crearEmpresa} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="rfc">RFC</Label>
                <Input
                  id="rfc"
                  value={rfc}
                  onChange={(e) => setRfc(e.target.value.toUpperCase())}
                  maxLength={13}
                  required
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="razon">Razón social</Label>
                <Input id="razon" value={razonSocial} onChange={(e) => setRazonSocial(e.target.value)} required />
              </div>
              {error && <p className="text-sm text-destructive">{error}</p>}
              <Button type="submit" disabled={submitting}>
                {submitting ? "Creando..." : "Crear empresa"}
              </Button>
            </form>
          </CardContent>
        </Card>
      </div>

      {empresaActiva && can(empresaActiva.permisos, PERM.CREDENCIALES_GESTIONAR) && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Conexión con el SAT — {empresaActiva.empresa.razon_social}</CardTitle>
          </CardHeader>
          <CardContent className="flex items-center justify-between">
            {credencial?.estado === "conectado" ? (
              <div className="flex items-center gap-2 text-sm">
                <CheckCircle2 className="h-4 w-4 text-[color:var(--status-good)]" />
                <span>
                  Conectado ({credencial.tipo.toUpperCase()})
                  {credencial.conectado_at && ` — desde ${formatDate(credencial.conectado_at)}`}
                </span>
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">Sin conexión con el SAT todavía.</p>
            )}
            <Button onClick={conectarSat} disabled={conectando} variant={credencial?.estado === "conectado" ? "outline" : "default"}>
              {conectando ? "Conectando..." : credencial?.estado === "conectado" ? "Reconectar" : "Conectar SAT"}
            </Button>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
