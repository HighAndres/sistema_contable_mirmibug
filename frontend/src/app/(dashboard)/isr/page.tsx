"use client";

import { useCallback, useEffect, useState } from "react";
import { Download, Settings2 } from "lucide-react";

import { useEmpresa } from "@/components/empresa-provider";
import { MESES_LARGO, PeriodoSelector } from "@/components/impuestos/periodo-selector";
import { StatTile } from "@/components/stat-tile";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ApiError, apiFetch } from "@/lib/api";
import { exportarExcel } from "@/lib/export-xlsx";
import { formatMoney2 } from "@/lib/format";
import { PERM, can } from "@/lib/permissions";
import type { Catalogo, ConfiguracionFiscal, IsrEjercicio, MecanicaIsr } from "@/lib/types";

const MECANICA_LABEL: Record<MecanicaIsr, string> = {
  pm_general: "Persona moral · régimen general (coeficiente de utilidad)",
  pm_resico: "Persona moral · RESICO (flujo de efectivo)",
  pf_resico: "Persona física · RESICO (tasa sobre ingresos)",
  pf_actividad: "Persona física · actividad empresarial y profesional (tarifa art. 96)",
  no_aplica: "No aplica (sueldos y salarios)",
};

export default function IsrPage() {
  const { empresaActiva, refresh } = useEmpresa();
  const hoy = new Date();
  const [anio, setAnio] = useState(hoy.getFullYear());
  const [hastaMes, setHastaMes] = useState<number>(hoy.getMonth() + 1);
  const [data, setData] = useState<IsrEjercicio | null>(null);
  const [loading, setLoading] = useState(true);

  // configuración fiscal
  const [openCfg, setOpenCfg] = useState(false);
  const [cfg, setCfg] = useState<ConfiguracionFiscal | null>(null);
  const [regimenes, setRegimenes] = useState<Catalogo[]>([]);
  const [regimen, setRegimen] = useState("");
  const [coef, setCoef] = useState("");
  const [guardando, setGuardando] = useState(false);
  const [errorCfg, setErrorCfg] = useState<string | null>(null);

  const cargar = useCallback(async () => {
    setLoading(true);
    try {
      setData(await apiFetch<IsrEjercicio>(`/impuestos/isr?anio=${anio}&hasta_mes=${hastaMes}`));
    } finally {
      setLoading(false);
    }
  }, [anio, hastaMes]);

  useEffect(() => {
    if (empresaActiva) void cargar();
  }, [empresaActiva, cargar]);

  async function abrirConfig() {
    setErrorCfg(null);
    const [c, r] = await Promise.all([
      apiFetch<ConfiguracionFiscal>("/impuestos/configuracion"),
      apiFetch<Catalogo[]>("/catalogs/regimen_fiscal").catch(() => [] as Catalogo[]),
    ]);
    setCfg(c);
    setRegimenes(r);
    setRegimen(c.regimen_fiscal_codigo ?? "");
    setCoef(c.coeficiente_utilidad != null ? String(c.coeficiente_utilidad) : "");
    setOpenCfg(true);
  }

  async function guardarConfig() {
    setGuardando(true);
    setErrorCfg(null);
    try {
      await apiFetch("/impuestos/configuracion", {
        method: "PUT",
        body: JSON.stringify({
          regimen_fiscal_codigo: regimen || null,
          coeficiente_utilidad: coef.trim() === "" ? null : Number(coef),
        }),
      });
      setOpenCfg(false);
      await Promise.all([cargar(), refresh()]);
    } catch (err) {
      setErrorCfg(err instanceof ApiError ? err.message : "No se pudo guardar");
    } finally {
      setGuardando(false);
    }
  }

  function exportar() {
    if (!data) return;
    exportarExcel(`isr-${empresaActiva!.empresa.rfc}-${anio}`, {
      ISR: data.meses.map((m) => ({
        Mes: MESES_LARGO[m.mes - 1],
        "Ingresos del mes": m.ingresos_mes,
        "Deducciones del mes": m.deducciones_mes,
        "Ingresos acumulados": m.ingresos_acumulados,
        "Deducciones acumuladas": m.deducciones_acumuladas,
        Base: m.base,
        Tasa: m.tasa_aplicada ?? "",
        "ISR acumulado": m.isr_acumulado,
        "Pagos anteriores": m.pagos_anteriores,
        "Pago provisional del mes": m.isr_del_mes,
      })),
    });
  }

  if (!empresaActiva) return null;
  const puedeConfigurar = can(empresaActiva.permisos, PERM.EMPRESAS_EDITAR);
  const ultimo = data?.meses[data.meses.length - 1];
  const esPM = data?.mecanica === "pm_general";
  const usaDeducciones = data?.mecanica === "pm_resico" || data?.mecanica === "pf_actividad";

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">ISR · pagos provisionales</h1>
          <p className="text-sm text-muted-foreground">
            Estimación del pago provisional mensual según el tipo de contribuyente, con los CFDI de la bóveda.
          </p>
        </div>
        <div className="flex gap-2">
          {puedeConfigurar && (
            <Button variant="outline" onClick={abrirConfig}>
              <Settings2 className="mr-2 h-4 w-4" /> Configuración fiscal
            </Button>
          )}
          <Button variant="outline" onClick={exportar} disabled={!data}>
            <Download className="mr-2 h-4 w-4" /> Exportar a Excel
          </Button>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <PeriodoSelector
          anio={anio}
          mes={hastaMes}
          anios={data?.anios_disponibles ?? [anio]}
          permitirAnual={false}
          etiquetaMes="Hasta el mes"
          onChange={(a, m) => {
            setAnio(a);
            setHastaMes(m ?? 12);
          }}
        />
        <span className="text-sm text-muted-foreground">Acumulado de enero a {MESES_LARGO[hastaMes - 1]} {anio}</span>
      </div>

      {data && (
        <>
          <Card>
            <CardContent className="flex flex-wrap items-center gap-3 p-4 text-sm">
              <Badge variant="outline">{data.tipo_persona === "moral" ? "Persona moral" : "Persona física"}</Badge>
              <Badge variant="outline">Régimen {data.regimen_fiscal_codigo ?? "sin configurar"}</Badge>
              {esPM && <Badge variant="outline">Coeficiente {data.coeficiente_utilidad ?? "—"}</Badge>}
              <span className="text-muted-foreground">{MECANICA_LABEL[data.mecanica]}</span>
            </CardContent>
          </Card>

          {data.advertencias.map((a) => (
            <p key={a} className="rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-sm">{a}</p>
          ))}

          {ultimo && (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <StatTile label={`Pago provisional ${MESES_LARGO[ultimo.mes - 1]}`} value={formatMoney2(ultimo.isr_del_mes)} tone="critical" hint="ISR acumulado − pagos anteriores" />
              <StatTile label="ISR acumulado del ejercicio" value={formatMoney2(ultimo.isr_acumulado)} />
              <StatTile label={esPM ? "Ingresos nominales acumulados" : "Ingresos cobrados acumulados"} value={formatMoney2(ultimo.ingresos_acumulados)} />
              <StatTile label={usaDeducciones ? "Deducciones acumuladas" : "Base gravable"} value={formatMoney2(usaDeducciones ? ultimo.deducciones_acumuladas : ultimo.base)} />
            </div>
          )}

          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-base">Cédula mensual</CardTitle>
              <p className="text-sm text-muted-foreground">{data.descripcion}</p>
            </CardHeader>
            <CardContent className="p-0">
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Mes</TableHead>
                      <TableHead className="text-right">{esPM ? "Ingresos nominales" : "Ingresos cobrados"}</TableHead>
                      {usaDeducciones && <TableHead className="text-right">Deducciones</TableHead>}
                      <TableHead className="text-right">Ingresos acum.</TableHead>
                      {usaDeducciones && <TableHead className="text-right">Deducciones acum.</TableHead>}
                      <TableHead className="text-right">{esPM ? "Utilidad fiscal est." : "Base"}</TableHead>
                      <TableHead className="text-right">Tasa</TableHead>
                      <TableHead className="text-right">ISR acumulado</TableHead>
                      <TableHead className="text-right">Pagos anteriores</TableHead>
                      <TableHead className="text-right font-semibold">Pago del mes</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody className={loading ? "opacity-50" : ""}>
                    {data.meses.map((m) => (
                      <TableRow key={m.mes}>
                        <TableCell className="font-medium">{MESES_LARGO[m.mes - 1]}</TableCell>
                        <TableCell className="text-right tabular-nums">{formatMoney2(m.ingresos_mes)}</TableCell>
                        {usaDeducciones && <TableCell className="text-right tabular-nums">{formatMoney2(m.deducciones_mes)}</TableCell>}
                        <TableCell className="text-right tabular-nums">{formatMoney2(m.ingresos_acumulados)}</TableCell>
                        {usaDeducciones && <TableCell className="text-right tabular-nums">{formatMoney2(m.deducciones_acumuladas)}</TableCell>}
                        <TableCell className="text-right tabular-nums">{formatMoney2(m.base)}</TableCell>
                        <TableCell className="text-right tabular-nums">{m.tasa_aplicada != null ? `${(m.tasa_aplicada * 100).toFixed(2)} %` : "tarifa"}</TableCell>
                        <TableCell className="text-right tabular-nums">{formatMoney2(m.isr_acumulado)}</TableCell>
                        <TableCell className="text-right tabular-nums">{formatMoney2(m.pagos_anteriores)}</TableCell>
                        <TableCell className="text-right font-semibold tabular-nums">{formatMoney2(m.isr_del_mes)}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </CardContent>
          </Card>

          <p className="text-xs text-muted-foreground">
            Estimación: no considera retenciones de ISR, PTU pagada, pérdidas fiscales de ejercicios anteriores,
            deducciones personales ni actualizaciones. Tarifa del art. 96 y tasas RESICO vigentes 2024-2025.
          </p>
        </>
      )}

      <Dialog open={openCfg} onOpenChange={setOpenCfg}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Configuración fiscal · {cfg?.razon_social}</DialogTitle>
            <DialogDescription>
              El tipo de persona se toma del RFC ({cfg?.rfc}: {cfg?.tipo_persona === "fisica" ? "física, 13 caracteres" : "moral, 12 caracteres"}). El régimen y el coeficiente definen la mecánica de ISR.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-1.5">
              <Label>Régimen fiscal</Label>
              <Select value={regimen} onValueChange={setRegimen}>
                <SelectTrigger><SelectValue placeholder="Selecciona el régimen" /></SelectTrigger>
                <SelectContent>
                  {regimenes.map((r) => (
                    <SelectItem key={r.codigo} value={r.codigo}>{r.codigo} · {r.nombre}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            {cfg?.tipo_persona === "moral" && regimen !== "626" && (
              <div className="space-y-1.5">
                <Label htmlFor="coef">Coeficiente de utilidad (art. 14 LISR)</Label>
                <Input id="coef" type="number" step="0.0001" min="0" max="1" placeholder="p. ej. 0.1234" value={coef} onChange={(e) => setCoef(e.target.value)} />
                <p className="text-xs text-muted-foreground">Utilidad fiscal ÷ ingresos nominales del último ejercicio de 12 meses con utilidad. Se aplica a los ingresos nominales acumulados.</p>
              </div>
            )}
            {errorCfg && <p className="text-sm text-destructive">{errorCfg}</p>}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpenCfg(false)}>Cancelar</Button>
            <Button onClick={guardarConfig} disabled={guardando}>{guardando ? "Guardando…" : "Guardar"}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
