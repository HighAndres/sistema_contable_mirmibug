"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Building2, CheckCircle2 } from "lucide-react";

import { useEmpresa } from "@/components/empresa-provider";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ApiError, apiFetch } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { PERM, can } from "@/lib/permissions";
import type { CredencialSat, RegimenFiscal } from "@/lib/types";

// Mismo patrón que el backend (tenants/schemas.py): 3 letras = PM, 4 = PF.
const RFC_RE = /^[A-ZÑ&]{3,4}[0-9]{6}[A-Z0-9]{3}$/;

/** Tipo de persona que define el propio RFC: 12 caracteres = moral, 13 = física. */
function tipoPersonaDeRfc(rfc: string): "fisica" | "moral" | null {
  if (rfc.length === 12) return "moral";
  if (rfc.length === 13) return "fisica";
  return null;
}

const MECANICA_LABEL: Record<RegimenFiscal["mecanica_isr"], string> = {
  pm_general: "ISR: ingresos nominales acumulados × coeficiente de utilidad × 30 %.",
  pm_resico: "ISR: (cobrado − pagado) acumulado × 30 % (RESICO personas morales).",
  pf_resico: "ISR: tasa del 1 % al 2.5 % sobre lo cobrado en el mes (RESICO personas físicas).",
  resico: "ISR simplificado de confianza según el tipo de persona.",
  pf_actividad: "ISR: ingresos cobrados − gastos pagados, tarifa del art. 96 acumulada.",
  no_aplica: "Sin pago provisional de ISR calculado por el sistema (lo retiene un tercero o no aplica).",
};

export default function EmpresasPage() {
  const { empresas, empresaActiva, seleccionarEmpresa, refresh } = useEmpresa();
  const [rfc, setRfc] = useState("");
  const [razonSocial, setRazonSocial] = useState("");
  const [regimen, setRegimen] = useState("");
  const [coeficiente, setCoeficiente] = useState("");
  const [regimenes, setRegimenes] = useState<RegimenFiscal[]>([]);
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

  useEffect(() => {
    apiFetch<RegimenFiscal[]>("/tenants/regimenes")
      .then(setRegimenes)
      .catch(() => setRegimenes([]));
  }, []);

  const tipoPersona = tipoPersonaDeRfc(rfc);
  const rfcValido = RFC_RE.test(rfc);
  // Solo los regímenes que aplican al tipo de persona del RFC capturado.
  const regimenesAplicables = useMemo(() => (tipoPersona ? regimenes.filter((r) => r.tipos_persona.includes(tipoPersona)) : []), [regimenes, tipoPersona]);
  const regimenSel = regimenes.find((r) => r.codigo === regimen) ?? null;
  const pideCoeficiente = tipoPersona === "moral" && regimenSel?.mecanica_isr === "pm_general";

  // Si cambia el RFC y el régimen elegido deja de aplicar, se limpia.
  useEffect(() => {
    if (regimen && !regimenesAplicables.some((r) => r.codigo === regimen)) setRegimen("");
  }, [regimen, regimenesAplicables]);

  async function crearEmpresa(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (!rfcValido) {
      setError("RFC inválido: 12 caracteres para persona moral o 13 para persona física.");
      return;
    }
    if (!regimen) {
      setError("Selecciona el régimen fiscal: define cómo se calcula el ISR.");
      return;
    }
    setSubmitting(true);
    try {
      const nueva = await apiFetch<{ id: string }>("/tenants/empresas", {
        method: "POST",
        body: JSON.stringify({
          rfc,
          razon_social: razonSocial,
          regimen_fiscal_codigo: regimen,
          coeficiente_utilidad: pideCoeficiente && coeficiente.trim() ? coeficiente.trim() : null,
        }),
      });
      setRfc("");
      setRazonSocial("");
      setRegimen("");
      setCoeficiente("");
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
            {empresas.length === 0 && <p className="text-sm text-muted-foreground">Aún no perteneces a ninguna empresa.</p>}
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
                <Input id="rfc" value={rfc} onChange={(e) => setRfc(e.target.value.toUpperCase().replace(/\s/g, ""))} maxLength={13} required />
                <p className="text-xs text-muted-foreground">
                  {tipoPersona === "moral" && "Persona moral (12 caracteres)."}
                  {tipoPersona === "fisica" && "Persona física (13 caracteres)."}
                  {!tipoPersona && "12 caracteres para persona moral, 13 para persona física."}
                  {tipoPersona && !rfcValido && " El formato no parece válido."}
                </p>
              </div>
              <div className="space-y-2">
                <Label htmlFor="razon">{tipoPersona === "fisica" ? "Nombre" : "Razón social"}</Label>
                <Input id="razon" value={razonSocial} onChange={(e) => setRazonSocial(e.target.value)} required />
              </div>
              <div className="space-y-2">
                <Label>Régimen fiscal</Label>
                <Select value={regimen} onValueChange={setRegimen} disabled={!tipoPersona}>
                  <SelectTrigger>
                    <SelectValue placeholder={tipoPersona ? "Selecciona el régimen" : "Captura primero el RFC"} />
                  </SelectTrigger>
                  <SelectContent>
                    {regimenesAplicables.map((r) => (
                      <SelectItem key={r.codigo} value={r.codigo}>
                        {r.codigo} · {r.nombre}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <p className="text-xs text-muted-foreground">
                  {regimenSel ? MECANICA_LABEL[regimenSel.mecanica_isr] : "Define la mecánica con la que se calcula el ISR provisional."}
                </p>
              </div>
              {pideCoeficiente && (
                <div className="space-y-2">
                  <Label htmlFor="coef">Coeficiente de utilidad (art. 14 LISR)</Label>
                  <Input
                    id="coef"
                    type="number"
                    step="0.0001"
                    min="0"
                    max="1"
                    placeholder="p. ej. 0.1234 — puedes capturarlo después"
                    value={coeficiente}
                    onChange={(e) => setCoeficiente(e.target.value)}
                  />
                  <p className="text-xs text-muted-foreground">
                    Utilidad fiscal ÷ ingresos nominales del último ejercicio con utilidad. Se aplica a los ingresos acumulados.
                  </p>
                </div>
              )}
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
                  Conectado ({credencial.tipo.toUpperCase()}){credencial.conectado_at && ` — desde ${formatDate(credencial.conectado_at)}`}
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
