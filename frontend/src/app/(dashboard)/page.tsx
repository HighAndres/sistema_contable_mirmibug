"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { ArrowDown, ArrowUp, Download, FileBadge, KeyRound, Settings2, ShieldCheck } from "lucide-react";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { useEmpresa } from "@/components/empresa-provider";
import { MESES_LARGO, PeriodoSelector } from "@/components/impuestos/periodo-selector";
import { StatTile } from "@/components/stat-tile";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ApiError, apiDownload, apiFetch } from "@/lib/api";
import { formatDate, formatMes, formatMoney } from "@/lib/format";
import { PERM, can } from "@/lib/permissions";
import { cn } from "@/lib/utils";
import type { DashboardKPIs, MesMonto, TopContraparte, VigenciaCertificado, Vigencias } from "@/lib/types";

// ---------- Tarjetas configurables ----------

type TileId = "ingresos" | "egresos" | "utilidad" | "iva" | "isr" | "cxc" | "cxp" | "alertas";

const TILES: { id: TileId; label: string; descripcion: string }[] = [
  { id: "ingresos", label: "Ingresos", descripcion: "Total de facturas de ingreso vigentes del periodo" },
  { id: "egresos", label: "Egresos", descripcion: "Total de facturas de gasto vigentes del periodo" },
  { id: "utilidad", label: "Utilidad", descripcion: "Ingresos − egresos" },
  { id: "iva", label: "IVA a cargo / a favor", descripcion: "Del apartado IVA (base flujo) para el periodo" },
  { id: "isr", label: "ISR estimado", descripcion: "Del apartado ISR: pago provisional del mes o acumulado del año" },
  { id: "cxc", label: "Cuentas por cobrar", descripcion: "Facturas PPD emitidas sin complemento de pago" },
  { id: "cxp", label: "Cuentas por pagar", descripcion: "Facturas PPD recibidas sin complemento de pago" },
  { id: "alertas", label: "CFDIs con alertas", descripcion: "Comprobantes marcados por el motor de validación" },
];
const TILES_DEFAULT: TileId[] = ["ingresos", "egresos", "utilidad", "iva", "isr", "cxc", "cxp"];

function storageKey(empresaId: string) {
  return `nubinox_dashboard_tiles_${empresaId}`;
}
function cargarTiles(empresaId: string): TileId[] {
  if (typeof window === "undefined") return TILES_DEFAULT;
  try {
    const raw = window.localStorage.getItem(storageKey(empresaId));
    if (!raw) return TILES_DEFAULT;
    const ids = (JSON.parse(raw) as string[]).filter((i): i is TileId => TILES.some((t) => t.id === i));
    return ids.length ? ids : TILES_DEFAULT;
  } catch {
    return TILES_DEFAULT;
  }
}

const SEVERIDAD_VARIANT = { alta: "destructive", media: "warning", baja: "success" } as const;

export default function DashboardPage() {
  const { empresaActiva } = useEmpresa();
  const hoy = new Date();
  const [anio, setAnio] = useState(hoy.getFullYear());
  const [mes, setMes] = useState<number | null>(hoy.getMonth() + 1);
  const [kpis, setKpis] = useState<DashboardKPIs | null>(null);
  const [mensual, setMensual] = useState<MesMonto[]>([]);
  const [topClientes, setTopClientes] = useState<TopContraparte[]>([]);
  const [topProveedores, setTopProveedores] = useState<TopContraparte[]>([]);
  const [vigencias, setVigencias] = useState<Vigencias | null>(null);
  const [loading, setLoading] = useState(true);
  const [descargando, setDescargando] = useState<string | null>(null);
  const [errorDescarga, setErrorDescarga] = useState<string | null>(null);

  const [tiles, setTiles] = useState<TileId[]>(TILES_DEFAULT);
  const [openCfg, setOpenCfg] = useState(false);
  const [tilesEdit, setTilesEdit] = useState<TileId[]>(TILES_DEFAULT);

  useEffect(() => {
    if (empresaActiva) setTiles(cargarTiles(empresaActiva.empresa.id));
  }, [empresaActiva]);

  const cargar = useCallback(async () => {
    setLoading(true);
    try {
      const p = new URLSearchParams({ anio: String(anio) });
      if (mes) p.set("mes", String(mes));
      const [k, m, c, pr, v] = await Promise.all([
        apiFetch<DashboardKPIs>(`/reports/dashboard?${p}`),
        apiFetch<MesMonto[]>(`/reports/mensual?anio=${anio}`),
        apiFetch<TopContraparte[]>(`/reports/top-clientes?${p}`),
        apiFetch<TopContraparte[]>(`/reports/top-proveedores?${p}`),
        apiFetch<Vigencias>("/credentials/vigencias").catch(() => null),
      ]);
      setKpis(k);
      setMensual(m);
      setTopClientes(c);
      setTopProveedores(pr);
      setVigencias(v);
    } finally {
      setLoading(false);
    }
  }, [anio, mes]);

  useEffect(() => {
    if (empresaActiva) void cargar();
  }, [empresaActiva, cargar]);

  const chartData = useMemo(() => mensual.map((m) => ({ ...m, label: formatMes(m.mes) })), [mensual]);

  function abrirConfig() {
    setTilesEdit(tiles);
    setOpenCfg(true);
  }
  function guardarConfig() {
    if (!empresaActiva) return;
    setTiles(tilesEdit);
    window.localStorage.setItem(storageKey(empresaActiva.empresa.id), JSON.stringify(tilesEdit));
    setOpenCfg(false);
  }
  function mover(id: TileId, dir: -1 | 1) {
    setTilesEdit((prev) => {
      const i = prev.indexOf(id);
      const j = i + dir;
      if (i < 0 || j < 0 || j >= prev.length) return prev;
      const copia = [...prev];
      [copia[i], copia[j]] = [copia[j], copia[i]];
      return copia;
    });
  }
  function toggle(id: TileId) {
    setTilesEdit((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  }

  async function descargar(tipo: "constancia" | "opinion") {
    if (!empresaActiva) return;
    setDescargando(tipo);
    setErrorDescarga(null);
    try {
      await apiDownload(`/sat/${tipo}`, `${tipo}_${empresaActiva.empresa.rfc}.pdf`);
    } catch (err) {
      setErrorDescarga(err instanceof ApiError ? err.message : "No se pudo descargar");
    } finally {
      setDescargando(null);
    }
  }

  if (!empresaActiva) return null;
  if (!kpis) return <p className="text-sm text-muted-foreground">Cargando dashboard...</p>;

  const periodoTxt = mes ? `${MESES_LARGO[mes - 1]} ${anio}` : `Ejercicio ${anio}`;
  const puedeCredenciales = can(empresaActiva.permisos, PERM.CREDENCIALES_GESTIONAR);

  function renderTile(id: TileId) {
    const k = kpis!;
    switch (id) {
      case "ingresos":
        return <StatTile key={id} label="Ingresos" value={formatMoney(k.ingresos_total)} hint={periodoTxt} />;
      case "egresos":
        return <StatTile key={id} label="Egresos" value={formatMoney(k.egresos_total)} hint={periodoTxt} />;
      case "utilidad":
        return <StatTile key={id} label="Utilidad" value={formatMoney(k.utilidad)} tone={k.utilidad >= 0 ? "good" : "critical"} hint="Ingresos − egresos" />;
      case "iva":
        return (
          <Link key={id} href="/iva" className="block">
            <StatTile
              label={k.iva_saldo >= 0 ? "IVA a cargo" : "IVA a favor"}
              value={formatMoney(Math.abs(k.iva_saldo))}
              tone={k.iva_saldo >= 0 ? "critical" : "good"}
              hint={`Base flujo · ${periodoTxt} · ver detalle →`}
            />
          </Link>
        );
      case "isr":
        return (
          <Link key={id} href="/isr" className="block">
            <StatTile
              label={mes ? "ISR pago provisional" : "ISR acumulado del ejercicio"}
              value={formatMoney(k.isr_estimado)}
              hint={`${MECANICA_CORTA[k.isr_mecanica] ?? k.isr_mecanica} · ver cédula →`}
            />
          </Link>
        );
      case "cxc":
        return (
          <Link key={id} href="/cfdi" className="block">
            <StatTile label="Cuentas por cobrar" value={formatMoney(k.cuentas_por_cobrar.total)} hint={`${k.cuentas_por_cobrar.num_cfdis} facturas PPD sin complemento`} />
          </Link>
        );
      case "cxp":
        return (
          <Link key={id} href="/cfdi" className="block">
            <StatTile label="Cuentas por pagar" value={formatMoney(k.cuentas_por_pagar.total)} hint={`${k.cuentas_por_pagar.num_cfdis} facturas PPD sin complemento`} />
          </Link>
        );
      case "alertas":
        return <StatTile key={id} label="CFDIs con alertas" value={`${k.cfdis_con_alertas} / ${k.cfdis_vigentes}`} tone={k.alertas_altas > 0 ? "critical" : "default"} hint={`${k.alertas_altas} altas · ${k.alertas_medias} medias`} />;
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Dashboard fiscal</h1>
          <p className="text-sm text-muted-foreground">{empresaActiva.empresa.razon_social} · {periodoTxt}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <PeriodoSelector anio={anio} mes={mes} anios={anios(hoy.getFullYear())} onChange={(a, m) => { setAnio(a); setMes(m); }} />
          <Button variant="outline" size="sm" onClick={abrirConfig}>
            <Settings2 className="mr-2 h-4 w-4" /> Personalizar
          </Button>
        </div>
      </div>

      <div className={cn("grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-4", loading && "opacity-60")}>
        {tiles.map(renderTile)}
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle className="text-base">Ingresos vs egresos · {anio}</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="viz-root h-72">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chartData} barGap={4}>
                  <CartesianGrid vertical={false} stroke="var(--chart-grid)" />
                  <XAxis dataKey="label" stroke="var(--chart-axis)" fontSize={12} tickLine={false} axisLine={false} />
                  <YAxis stroke="var(--chart-axis)" fontSize={12} tickLine={false} axisLine={false} tickFormatter={(v) => formatMoney(Number(v))} width={90} />
                  <Tooltip formatter={(value: number) => formatMoney(value)} />
                  <Legend />
                  <Bar dataKey="ingresos" name="Ingresos" fill="var(--chart-series-1)" radius={[4, 4, 0, 0]} />
                  <Bar dataKey="egresos" name="Egresos" fill="var(--chart-series-2)" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Alertas de validación</CardTitle>
            <p className="text-xs text-muted-foreground">
              El motor de reglas revisa cada CFDI sincronizado y marca los que tienen un riesgo fiscal. Estas son las reglas activas y cuántos comprobantes del periodo tocan:
            </p>
          </CardHeader>
          <CardContent className="space-y-3">
            <p className="text-sm">
              <span className="font-semibold">{kpis.cfdis_con_alertas}</span> de {kpis.cfdis_vigentes} CFDIs con alguna alerta
            </p>
            <div className="flex flex-wrap gap-2">
              <Badge variant="destructive">{kpis.alertas_altas} altas</Badge>
              <Badge variant="warning">{kpis.alertas_medias} medias</Badge>
              <Badge variant="success">{kpis.alertas_bajas} bajas</Badge>
            </div>
            <ul className="space-y-2 text-sm">
              {kpis.alertas_por_regla.length === 0 && <li className="text-muted-foreground">Sin alertas en el periodo.</li>}
              {kpis.alertas_por_regla.map((a) => (
                <li key={a.regla_codigo} className="flex items-start gap-2">
                  <Badge variant={SEVERIDAD_VARIANT[a.severidad]} className="mt-0.5 shrink-0">{a.cfdis}</Badge>
                  <span className="text-muted-foreground">{a.descripcion}</span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <TablaTop titulo="Top clientes" col="Cliente" filas={topClientes} />
        <TablaTop titulo="Top proveedores" col="Proveedor" filas={topProveedores} />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base"><KeyRound className="h-4 w-4" /> Vigencia de e.firma y sellos</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {!vigencias || !vigencias.conectado ? (
              <p className="text-sm text-muted-foreground">
                La empresa no tiene conexión con el SAT.{" "}
                {puedeCredenciales && <Link href="/empresas" className="text-primary underline">Conéctala en Empresas</Link>}
              </p>
            ) : (
              <>
                <FilaVigencia titulo="e.firma (FIEL)" v={vigencias.fiel} />
                <FilaVigencia titulo="Certificado de sello digital (CSD)" v={vigencias.csd} />
              </>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base"><FileBadge className="h-4 w-4" /> Documentos del SAT</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <p className="text-sm text-muted-foreground">Descarga la constancia de situación fiscal y la opinión de cumplimiento (simulados; con la conexión real se obtienen del portal del SAT con la e.firma).</p>
            <div className="flex flex-wrap gap-2">
              <Button variant="outline" onClick={() => descargar("constancia")} disabled={!!descargando}>
                <Download className="mr-2 h-4 w-4" /> {descargando === "constancia" ? "Generando…" : "Constancia de situación fiscal"}
              </Button>
              <Button variant="outline" onClick={() => descargar("opinion")} disabled={!!descargando}>
                <ShieldCheck className="mr-2 h-4 w-4" /> {descargando === "opinion" ? "Generando…" : "Opinión de cumplimiento"}
              </Button>
            </div>
            {errorDescarga && <p className="text-sm text-destructive">{errorDescarga}</p>}
          </CardContent>
        </Card>
      </div>

      <Dialog open={openCfg} onOpenChange={setOpenCfg}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Personalizar dashboard</DialogTitle>
            <DialogDescription>Elige qué tarjetas ver y en qué orden. Se guarda en este navegador para {empresaActiva.empresa.razon_social}.</DialogDescription>
          </DialogHeader>
          <ul className="space-y-1">
            {[...tilesEdit, ...TILES.map((t) => t.id).filter((id) => !tilesEdit.includes(id))].map((id) => {
              const t = TILES.find((x) => x.id === id)!;
              const activo = tilesEdit.includes(id);
              const idx = tilesEdit.indexOf(id);
              return (
                <li key={id} className={cn("flex items-center gap-2 rounded-md border p-2", !activo && "opacity-60")}>
                  <input type="checkbox" className="h-4 w-4" checked={activo} onChange={() => toggle(id)} aria-label={`Mostrar ${t.label}`} />
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium">{t.label}</p>
                    <p className="truncate text-xs text-muted-foreground">{t.descripcion}</p>
                  </div>
                  {activo && (
                    <div className="flex gap-1">
                      <Button variant="ghost" size="icon" className="h-7 w-7" aria-label="Subir" disabled={idx === 0} onClick={() => mover(id, -1)}><ArrowUp className="h-3.5 w-3.5" /></Button>
                      <Button variant="ghost" size="icon" className="h-7 w-7" aria-label="Bajar" disabled={idx === tilesEdit.length - 1} onClick={() => mover(id, 1)}><ArrowDown className="h-3.5 w-3.5" /></Button>
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setTilesEdit(TILES_DEFAULT)}>Restablecer</Button>
            <Button variant="outline" onClick={() => setOpenCfg(false)}>Cancelar</Button>
            <Button onClick={guardarConfig}>Guardar</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

const MECANICA_CORTA: Record<string, string> = {
  pm_general: "PM coeficiente de utilidad",
  pm_resico: "PM RESICO",
  pf_resico: "PF RESICO",
  pf_actividad: "PF actividad empresarial",
  no_aplica: "No aplica",
};

function anios(actual: number): number[] {
  return [actual, actual - 1, actual - 2];
}

function TablaTop({ titulo, col, filas }: { titulo: string; col: string; filas: TopContraparte[] }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{titulo}</CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>RFC</TableHead>
              <TableHead>{col}</TableHead>
              <TableHead className="text-right">CFDIs</TableHead>
              <TableHead className="text-right">Monto</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {filas.length === 0 && (
              <TableRow><TableCell colSpan={4} className="py-6 text-center text-muted-foreground">Sin datos en el periodo</TableCell></TableRow>
            )}
            {filas.map((c) => (
              <TableRow key={c.rfc}>
                <TableCell className="font-mono text-xs">{c.rfc}</TableCell>
                <TableCell className="max-w-64 truncate" title={c.nombre}>{c.nombre}</TableCell>
                <TableCell className="text-right">{c.num_cfdis}</TableCell>
                <TableCell className="text-right tabular-nums">{formatMoney(c.monto_total)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}

function FilaVigencia({ titulo, v }: { titulo: string; v: VigenciaCertificado }) {
  const variant = v.estado === "vencida" ? "destructive" : v.estado === "por_vencer" ? "warning" : v.estado === "vigente" ? "success" : "secondary";
  const texto =
    v.estado === "sin_datos" ? "Sin datos" :
    v.estado === "vencida" ? `Venció hace ${Math.abs(v.dias_restantes ?? 0)} días` :
    v.estado === "por_vencer" ? `Vence en ${v.dias_restantes} días` :
    `Vigente · ${v.dias_restantes} días`;
  return (
    <div className="flex items-center justify-between gap-3 rounded-md border p-3">
      <div className="min-w-0">
        <p className="text-sm font-medium">{titulo}</p>
        <p className="truncate font-mono text-xs text-muted-foreground">
          {v.numero_serie ? `Serie ${v.numero_serie}` : "—"}{v.vence ? ` · vence ${formatDate(v.vence)}` : ""}
        </p>
      </div>
      <Badge variant={variant} className="shrink-0">{texto}</Badge>
    </div>
  );
}
