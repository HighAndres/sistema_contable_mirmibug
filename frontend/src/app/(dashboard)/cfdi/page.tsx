"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Download, FileCode2, FileUp, RefreshCw, Search, X } from "lucide-react";

import { useEmpresa } from "@/components/empresa-provider";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ApiError, apiDownload, apiFetch } from "@/lib/api";
import { exportarExcel } from "@/lib/export-xlsx";
import { formatDate, formatMoney, formatMoney2 } from "@/lib/format";
import { PERM, can } from "@/lib/permissions";
import { cn } from "@/lib/utils";
import type { CargaXmlResponse, Catalogo, CfdiDetalle, CfdiEstatus, CfdiPage, CfdiResumen, CfdiTipo } from "@/lib/types";

const SEVERIDAD_VARIANT = { alta: "destructive", media: "warning", baja: "success" } as const;

const TODOS = "__todos__";
type TabTipo = "todos" | CfdiTipo;

const TABS: { value: TabTipo; label: string; descripcion: string }[] = [
  { value: "ingreso", label: "Ingresos", descripcion: "Facturas emitidas por la empresa (ventas)" },
  { value: "egreso", label: "Gastos", descripcion: "Facturas recibidas de proveedores (compras y gastos)" },
  { value: "nomina", label: "Nómina", descripcion: "Recibos de nómina emitidos a los empleados" },
  { value: "pago", label: "Pagos", descripcion: "Complementos de pago (REP) emitidos y recibidos" },
  { value: "nota_credito", label: "Notas de crédito", descripcion: "CFDI de egreso (tipo E): devoluciones, descuentos y bonificaciones" },
  { value: "todos", label: "Todos", descripcion: "Todos los comprobantes" },
];

const MESES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"];

const ESTATUS_LABEL: Record<CfdiEstatus, string> = {
  vigente: "Vigente",
  cancelado: "Cancelado",
  en_proceso: "En proceso de cancelación",
};
const ESTATUS_VARIANT: Record<CfdiEstatus, "secondary" | "destructive" | "warning"> = {
  vigente: "secondary",
  cancelado: "destructive",
  en_proceso: "warning",
};
const TIPO_LABEL: Record<CfdiTipo, string> = { ingreso: "Ingreso", egreso: "Gasto", pago: "Pago", nomina: "Nómina", nota_credito: "Nota de crédito" };

interface Filtros {
  estatus: string;
  emisor: string;
  receptor: string;
  anio: string;
  mes: string;
  metodo: string;
  forma: string;
  q: string;
}

const FILTROS_VACIOS: Filtros = { estatus: TODOS, emisor: "", receptor: "", anio: TODOS, mes: TODOS, metodo: TODOS, forma: TODOS, q: "" };
const PAGE_SIZE = 100;

export default function CfdiPageRoute() {
  const { empresaActiva } = useEmpresa();
  const [tab, setTab] = useState<TabTipo>("ingreso");
  const [filtros, setFiltros] = useState<Filtros>(FILTROS_VACIOS);
  const [aplicados, setAplicados] = useState<Filtros>(FILTROS_VACIOS);
  const [offset, setOffset] = useState(0);
  const [page, setPage] = useState<CfdiPage | null>(null);
  const [resumen, setResumen] = useState<CfdiResumen | null>(null);
  const [formasPago, setFormasPago] = useState<Catalogo[]>([]);
  const [loading, setLoading] = useState(true);
  const [sincronizando, setSincronizando] = useState(false);
  const [detalle, setDetalle] = useState<CfdiDetalle | null>(null);

  // --- carga de XML / ZIP ---
  const [openXml, setOpenXml] = useState(false);
  const [archivosXml, setArchivosXml] = useState<FileList | null>(null);
  const [cargandoXml, setCargandoXml] = useState(false);
  const [resXml, setResXml] = useState<CargaXmlResponse | null>(null);
  const [errorXml, setErrorXml] = useState<string | null>(null);

  async function cargarXml() {
    if (!archivosXml || archivosXml.length === 0) {
      setErrorXml("Selecciona uno o varios .xml o un .zip");
      return;
    }
    setCargandoXml(true);
    setErrorXml(null);
    try {
      const form = new FormData();
      Array.from(archivosXml).forEach((f) => form.append("archivos", f));
      setResXml(await apiFetch<CargaXmlResponse>("/sat/cargar-xml", { method: "POST", body: form }));
      await cargar();
    } catch (err) {
      setErrorXml(err instanceof ApiError ? err.message : "Error al cargar los XML");
    } finally {
      setCargandoXml(false);
    }
  }

  const formaNombre = useMemo(() => Object.fromEntries(formasPago.map((f) => [f.codigo, f.nombre])), [formasPago]);

  const buildParams = useCallback(
    (conTipo: boolean) => {
      const p = new URLSearchParams();
      if (conTipo && tab !== "todos") p.set("tipo", tab);
      if (aplicados.estatus !== TODOS) p.set("estatus", aplicados.estatus);
      if (aplicados.emisor.trim()) p.set("emisor", aplicados.emisor.trim());
      if (aplicados.receptor.trim()) p.set("receptor", aplicados.receptor.trim());
      if (aplicados.anio !== TODOS) p.set("anio", aplicados.anio);
      if (aplicados.mes !== TODOS) p.set("mes", aplicados.mes);
      if (aplicados.metodo !== TODOS) p.set("metodo_pago", aplicados.metodo);
      if (aplicados.forma !== TODOS) p.set("forma_pago", aplicados.forma);
      if (aplicados.q.trim()) p.set("q", aplicados.q.trim());
      return p;
    },
    [tab, aplicados],
  );

  const cargar = useCallback(async () => {
    setLoading(true);
    try {
      const pl = buildParams(true);
      pl.set("limit", String(PAGE_SIZE));
      pl.set("offset", String(offset));
      const [pg, rs] = await Promise.all([
        apiFetch<CfdiPage>(`/cfdi?${pl.toString()}`),
        apiFetch<CfdiResumen>(`/cfdi/resumen?${buildParams(false).toString()}`),
      ]);
      setPage(pg);
      setResumen(rs);
    } finally {
      setLoading(false);
    }
  }, [buildParams, offset]);

  useEffect(() => {
    if (empresaActiva) void cargar();
  }, [empresaActiva, cargar]);

  useEffect(() => {
    if (!empresaActiva) return;
    apiFetch<Catalogo[]>("/catalogs/forma_pago").then(setFormasPago).catch(() => setFormasPago([]));
  }, [empresaActiva]);

  function aplicarFiltros() {
    setOffset(0);
    setAplicados(filtros);
  }
  function limpiarFiltros() {
    setFiltros(FILTROS_VACIOS);
    setAplicados(FILTROS_VACIOS);
    setOffset(0);
  }
  function cambiarTab(v: string) {
    setTab(v as TabTipo);
    setOffset(0);
  }

  async function sincronizar() {
    setSincronizando(true);
    try {
      await apiFetch("/sat/sincronizar", { method: "POST" });
      await cargar();
    } finally {
      setSincronizando(false);
    }
  }

  async function verDetalle(id: string) {
    setDetalle(await apiFetch<CfdiDetalle>(`/cfdi/${id}`));
  }

  function exportar() {
    if (!page) return;
    const hoja = TABS.find((t) => t.value === tab)?.label ?? "CFDI";
    exportarExcel(`nubinox-cfdi-${hoja.toLowerCase()}-${empresaActiva!.empresa.rfc}`, {
      [hoja]: page.items.map((c) => ({
        Fecha: c.fecha,
        UUID: c.uuid_fiscal,
        Serie: c.serie ?? "",
        Folio: c.folio ?? "",
        Versión: c.version ?? "",
        Tipo: TIPO_LABEL[c.tipo],
        Dirección: c.direccion,
        "RFC emisor": c.rfc_emisor,
        Emisor: c.nombre_emisor,
        "RFC receptor": c.rfc_receptor,
        Receptor: c.nombre_receptor,
        "Método de pago": c.metodo_pago_codigo ?? "",
        "Forma de pago": c.forma_pago_codigo ? `${c.forma_pago_codigo} ${formaNombre[c.forma_pago_codigo] ?? ""}`.trim() : "",
        "Uso CFDI": c.uso_cfdi_codigo ?? "",
        Subtotal: c.subtotal,
        IVA: c.iva,
        Total: c.total,
        Estatus: ESTATUS_LABEL[c.estatus],
      })),
    });
  }

  if (!empresaActiva) return null;
  const permisos = empresaActiva.permisos;
  const hayFiltros = JSON.stringify(aplicados) !== JSON.stringify(FILTROS_VACIOS);
  const tabActual = TABS.find((t) => t.value === tab)!;
  const anios = resumen?.anios ?? [];
  const totalPaginas = page ? Math.max(1, Math.ceil(page.total / PAGE_SIZE)) : 1;
  const paginaActual = Math.floor(offset / PAGE_SIZE) + 1;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">CFDI</h1>
          <p className="text-sm text-muted-foreground">{tabActual.descripcion}</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={exportar} disabled={!page?.items.length}>
            <Download className="mr-2 h-4 w-4" /> Exportar a Excel
          </Button>
          {can(permisos, PERM.SAT_SINCRONIZAR) && (
            <Button variant="outline" onClick={() => { setArchivosXml(null); setResXml(null); setErrorXml(null); setOpenXml(true); }}>
              <FileUp className="mr-2 h-4 w-4" /> Cargar XML / ZIP
            </Button>
          )}
          {can(permisos, PERM.SAT_SINCRONIZAR) && (
            <Button onClick={sincronizar} disabled={sincronizando}>
              <RefreshCw className={cn("mr-2 h-4 w-4", sincronizando && "animate-spin")} />
              {sincronizando ? "Sincronizando..." : "Sincronizar con SAT"}
            </Button>
          )}
        </div>
      </div>

      <Tabs value={tab} onValueChange={cambiarTab}>
        <TabsList className="h-auto flex-wrap">
          {TABS.map((t) => (
            <TabsTrigger key={t.value} value={t.value} className="px-4 py-2">
              {t.label}
              {resumen && t.value !== "todos" && (
                <span className="ml-2 rounded-full bg-muted px-2 py-0.5 text-xs tabular-nums text-muted-foreground">
                  {resumen[t.value].cantidad}
                </span>
              )}
            </TabsTrigger>
          ))}
        </TabsList>
      </Tabs>

      {resumen && (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
          <TarjetaTipo titulo="Ingresos" r={resumen.ingreso} activa={tab === "ingreso"} onClick={() => cambiarTab("ingreso")} extra="Emitidas" />
          <TarjetaTipo titulo="Gastos" r={resumen.egreso} activa={tab === "egreso"} onClick={() => cambiarTab("egreso")} extra="Recibidas" />
          <TarjetaTipo titulo="Nómina" r={resumen.nomina} activa={tab === "nomina"} onClick={() => cambiarTab("nomina")} extra="Recibos" sinIva />
          <TarjetaTipo titulo="Pagos" r={resumen.pago} activa={tab === "pago"} onClick={() => cambiarTab("pago")} extra="Complementos (REP)" sinIva />
          <TarjetaTipo titulo="Notas de crédito" r={resumen.nota_credito} activa={tab === "nota_credito"} onClick={() => cambiarTab("nota_credito")} extra="Tipo E" />
        </div>
      )}

      <Card>
        <CardContent className="space-y-3 p-4">
          <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-4">
            <div className="relative xl:col-span-2">
              <Search className="pointer-events-none absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
              <Input
                className="pl-8"
                placeholder="Buscar por UUID, serie/folio, RFC o nombre…"
                value={filtros.q}
                onChange={(e) => setFiltros({ ...filtros, q: e.target.value })}
                onKeyDown={(e) => e.key === "Enter" && aplicarFiltros()}
              />
            </div>
            <Input
              placeholder="Emisor (RFC o nombre)"
              value={filtros.emisor}
              onChange={(e) => setFiltros({ ...filtros, emisor: e.target.value })}
              onKeyDown={(e) => e.key === "Enter" && aplicarFiltros()}
            />
            <Input
              placeholder="Receptor (RFC o nombre)"
              value={filtros.receptor}
              onChange={(e) => setFiltros({ ...filtros, receptor: e.target.value })}
              onKeyDown={(e) => e.key === "Enter" && aplicarFiltros()}
            />
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Select value={filtros.estatus} onValueChange={(v) => setFiltros({ ...filtros, estatus: v })}>
              <SelectTrigger className="w-[190px]"><SelectValue placeholder="Estatus" /></SelectTrigger>
              <SelectContent>
                <SelectItem value={TODOS}>Todos los estatus</SelectItem>
                <SelectItem value="vigente">Vigente</SelectItem>
                <SelectItem value="cancelado">Cancelado</SelectItem>
                <SelectItem value="en_proceso">En proceso de cancelación</SelectItem>
              </SelectContent>
            </Select>
            <Select value={filtros.anio} onValueChange={(v) => setFiltros({ ...filtros, anio: v })}>
              <SelectTrigger className="w-[120px]"><SelectValue placeholder="Año" /></SelectTrigger>
              <SelectContent>
                <SelectItem value={TODOS}>Todo año</SelectItem>
                {anios.map((a) => (
                  <SelectItem key={a} value={String(a)}>{a}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select value={filtros.mes} onValueChange={(v) => setFiltros({ ...filtros, mes: v })}>
              <SelectTrigger className="w-[120px]"><SelectValue placeholder="Mes" /></SelectTrigger>
              <SelectContent>
                <SelectItem value={TODOS}>Todo mes</SelectItem>
                {MESES.map((m, i) => (
                  <SelectItem key={m} value={String(i + 1)}>{m}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select value={filtros.metodo} onValueChange={(v) => setFiltros({ ...filtros, metodo: v })}>
              <SelectTrigger className="w-[150px]"><SelectValue placeholder="Método" /></SelectTrigger>
              <SelectContent>
                <SelectItem value={TODOS}>PUE y PPD</SelectItem>
                <SelectItem value="PUE">PUE · una exhibición</SelectItem>
                <SelectItem value="PPD">PPD · parcialidades</SelectItem>
              </SelectContent>
            </Select>
            <Select value={filtros.forma} onValueChange={(v) => setFiltros({ ...filtros, forma: v })}>
              <SelectTrigger className="w-[220px]"><SelectValue placeholder="Forma de pago" /></SelectTrigger>
              <SelectContent>
                <SelectItem value={TODOS}>Toda forma de pago</SelectItem>
                {formasPago.map((f) => (
                  <SelectItem key={f.codigo} value={f.codigo}>{f.codigo} · {f.nombre}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <div className="ml-auto flex gap-2">
              {hayFiltros && (
                <Button variant="ghost" onClick={limpiarFiltros}>
                  <X className="mr-1 h-4 w-4" /> Limpiar
                </Button>
              )}
              <Button variant="secondary" onClick={aplicarFiltros}>Aplicar filtros</Button>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Fecha</TableHead>
                  <TableHead>UUID</TableHead>
                  <TableHead className="whitespace-nowrap">Serie / Folio</TableHead>
                  {tab === "todos" && <TableHead>Tipo</TableHead>}
                  <TableHead>Emisor</TableHead>
                  <TableHead>Receptor</TableHead>
                  <TableHead>Método</TableHead>
                  <TableHead className="whitespace-nowrap">Forma de pago</TableHead>
                  <TableHead className="text-right">Subtotal</TableHead>
                  <TableHead className="text-right">Total</TableHead>
                  <TableHead>Estatus</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {loading && (
                  <TableRow>
                    <TableCell colSpan={11} className="py-8 text-center text-muted-foreground">Cargando...</TableCell>
                  </TableRow>
                )}
                {!loading &&
                  page?.items.map((c) => (
                    <TableRow key={c.id} className="cursor-pointer" onClick={() => verDetalle(c.id)}>
                      <TableCell className="whitespace-nowrap">{formatDate(c.fecha)}</TableCell>
                      <TableCell className="whitespace-nowrap font-mono text-xs" title={c.uuid_fiscal}>
                        {c.uuid_fiscal.slice(0, 8)}…{c.uuid_fiscal.slice(-4)}
                      </TableCell>
                      <TableCell className="whitespace-nowrap font-mono text-xs">{[c.serie, c.folio].filter(Boolean).join("-") || "—"}</TableCell>
                      {tab === "todos" && <TableCell>{TIPO_LABEL[c.tipo]}</TableCell>}
                      <TableCell className="max-w-56">
                        <span className="block truncate" title={c.nombre_emisor}>{c.nombre_emisor}</span>
                        <span className="font-mono text-xs text-muted-foreground">{c.rfc_emisor}</span>
                      </TableCell>
                      <TableCell className="max-w-56">
                        <span className="block truncate" title={c.nombre_receptor}>{c.nombre_receptor}</span>
                        <span className="font-mono text-xs text-muted-foreground">{c.rfc_receptor}</span>
                      </TableCell>
                      <TableCell>
                        {c.metodo_pago_codigo ? (
                          <Badge variant={c.metodo_pago_codigo === "PPD" ? "warning" : "outline"}>{c.metodo_pago_codigo}</Badge>
                        ) : (
                          <span className="text-muted-foreground">—</span>
                        )}
                      </TableCell>
                      <TableCell className="max-w-40 truncate text-xs" title={c.forma_pago_codigo ? formaNombre[c.forma_pago_codigo] : ""}>
                        {c.forma_pago_codigo ? `${c.forma_pago_codigo} · ${formaNombre[c.forma_pago_codigo] ?? ""}` : "—"}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">{formatMoney(c.subtotal)}</TableCell>
                      <TableCell className="text-right font-medium tabular-nums">{formatMoney(c.total)}</TableCell>
                      <TableCell>
                        <Badge variant={ESTATUS_VARIANT[c.estatus]}>{c.estatus === "en_proceso" ? "En proceso" : ESTATUS_LABEL[c.estatus]}</Badge>
                      </TableCell>
                    </TableRow>
                  ))}
                {!loading && page?.items.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={11} className="py-8 text-center text-muted-foreground">
                      {hayFiltros ? "Sin CFDIs con esos filtros." : 'Sin CFDIs. Usa "Sincronizar con SAT" para traer datos.'}
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </div>
          {page && page.total > PAGE_SIZE && (
            <div className="flex items-center justify-between border-t px-4 py-2 text-sm text-muted-foreground">
              <span>
                {offset + 1}–{Math.min(offset + PAGE_SIZE, page.total)} de {page.total}
              </span>
              <div className="flex gap-2">
                <Button variant="outline" size="sm" disabled={paginaActual <= 1} onClick={() => setOffset(offset - PAGE_SIZE)}>Anterior</Button>
                <span className="self-center">{paginaActual} / {totalPaginas}</span>
                <Button variant="outline" size="sm" disabled={paginaActual >= totalPaginas} onClick={() => setOffset(offset + PAGE_SIZE)}>Siguiente</Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      <Dialog open={!!detalle} onOpenChange={(open) => !open && setDetalle(null)}>
        <DialogContent className="max-w-2xl">
          {detalle && (
            <>
              <DialogHeader>
                <DialogTitle className="flex flex-wrap items-center gap-2">
                  {TIPO_LABEL[detalle.tipo]} {[detalle.serie, detalle.folio].filter(Boolean).join("-")}
                  <Badge variant={ESTATUS_VARIANT[detalle.estatus]}>{ESTATUS_LABEL[detalle.estatus]}</Badge>
                </DialogTitle>
                <p className="font-mono text-xs text-muted-foreground">{detalle.uuid_fiscal}</p>
              </DialogHeader>
              <div className="space-y-4 text-sm">
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <p className="text-muted-foreground">Emisor</p>
                    <p className="font-medium">{detalle.nombre_emisor}</p>
                    <p className="font-mono text-xs">{detalle.rfc_emisor}</p>
                  </div>
                  <div>
                    <p className="text-muted-foreground">Receptor</p>
                    <p className="font-medium">{detalle.nombre_receptor}</p>
                    <p className="font-mono text-xs">{detalle.rfc_receptor}</p>
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-x-6 gap-y-1 rounded-md border p-3 sm:grid-cols-3">
                  <Dato k="Fecha" v={formatDate(detalle.fecha)} />
                  <Dato k="Versión" v={detalle.version ?? "—"} />
                  <Dato k="Dirección" v={detalle.direccion === "emitido" ? "Emitido" : "Recibido"} />
                  <Dato k="Método de pago" v={detalle.metodo_pago_codigo ? `${detalle.metodo_pago_codigo} · ${detalle.metodo_pago_codigo === "PUE" ? "una sola exhibición" : "parcialidades o diferido"}` : "—"} />
                  <Dato k="Forma de pago" v={detalle.forma_pago_codigo ? `${detalle.forma_pago_codigo} · ${formaNombre[detalle.forma_pago_codigo] ?? ""}` : "—"} />
                  <Dato k="Uso CFDI" v={detalle.uso_cfdi_codigo ?? "—"} />
                </div>

                {detalle.metodo_pago_codigo === "PPD" && (
                  <div className="space-y-2 rounded-md border p-3">
                    <div className="flex items-center justify-between">
                      <p className="font-medium">Complementos de pago recibidos</p>
                      <Badge variant={(detalle.saldo_pendiente ?? 0) > 0 ? "warning" : "success"}>
                        {(detalle.saldo_pendiente ?? 0) > 0 ? `Saldo pendiente ${formatMoney2(detalle.saldo_pendiente ?? 0)}` : "Pagada"}
                      </Badge>
                    </div>
                    {detalle.pagos_recibidos.length === 0 ? (
                      <p className="text-xs text-muted-foreground">Ningún REP la paga todavía (cuenta por cobrar / pagar).</p>
                    ) : (
                      <ul className="space-y-1 text-xs">
                        {detalle.pagos_recibidos.map((p) => (
                          <li key={p.cfdi_pago_id + p.uuid_relacionado} className="flex justify-between gap-2">
                            <span>Parcialidad {p.num_parcialidad ?? "—"} · {p.fecha_pago ? formatDate(p.fecha_pago) : "—"} · <span className="font-mono">{p.uuid_pago.slice(0, 8)}…</span></span>
                            <span className="tabular-nums">{formatMoney2(p.imp_pagado)}{p.imp_saldo_insoluto != null ? ` · resta ${formatMoney2(p.imp_saldo_insoluto)}` : ""}</span>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                )}
                {detalle.pagos_relacionados.length > 0 && (
                  <div className="space-y-2 rounded-md border p-3">
                    <p className="font-medium">Documentos que paga este REP</p>
                    <ul className="space-y-1 text-xs">
                      {detalle.pagos_relacionados.map((p) => (
                        <li key={p.uuid_relacionado + String(p.num_parcialidad)} className="flex justify-between gap-2">
                          <span><span className="font-mono">{p.uuid_relacionado}</span> · parcialidad {p.num_parcialidad ?? "—"}</span>
                          <span className="tabular-nums">{formatMoney2(p.imp_pagado)}{p.imp_saldo_insoluto != null ? ` · resta ${formatMoney2(p.imp_saldo_insoluto)}` : ""}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                {detalle.alertas.length > 0 && (
                  <div className="space-y-2">
                    <p className="font-medium">Alertas de validación</p>
                    {detalle.alertas.map((a) => (
                      <div key={a.id} className="flex items-start gap-2">
                        <Badge variant={SEVERIDAD_VARIANT[a.severidad]}>{a.severidad}</Badge>
                        <p className="text-muted-foreground">{a.detalle}</p>
                      </div>
                    ))}
                  </div>
                )}

                <div>
                  <p className="mb-2 font-medium">Conceptos</p>
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Descripción</TableHead>
                        <TableHead className="text-right">Cant.</TableHead>
                        <TableHead className="text-right">V. unitario</TableHead>
                        <TableHead className="text-right">Importe</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {detalle.conceptos.map((c) => (
                        <TableRow key={c.id}>
                          <TableCell>{c.descripcion}</TableCell>
                          <TableCell className="text-right">{c.cantidad}</TableCell>
                          <TableCell className="text-right tabular-nums">{formatMoney2(c.valor_unitario)}</TableCell>
                          <TableCell className="text-right tabular-nums">{formatMoney2(c.importe)}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>

                <div className="flex items-end justify-between gap-4">
                  <div className="text-xs text-muted-foreground">
                    {detalle.origen === "mock" ? "CFDI simulado (demo)" : detalle.origen === "xml" ? "Cargado desde XML" : "Descargado del SAT"}
                    {detalle.tiene_xml && (
                      <Button variant="link" size="sm" className="ml-1 h-auto p-0 text-xs" onClick={() => apiDownload(`/sat/xml/${detalle.id}`, `${detalle.uuid_fiscal}.xml`)}>
                        <FileCode2 className="mr-1 h-3 w-3" /> Descargar XML
                      </Button>
                    )}
                  </div>
                  <div className="flex gap-6 text-right">
                  <div>
                    <p className="text-muted-foreground">Subtotal</p>
                    <p className="tabular-nums">{formatMoney2(detalle.subtotal)}</p>
                  </div>
                  <div>
                    <p className="text-muted-foreground">IVA</p>
                    <p className="tabular-nums">{formatMoney2(detalle.iva)}</p>
                  </div>
                  <div>
                    <p className="text-muted-foreground">Total</p>
                    <p className="font-semibold tabular-nums">{formatMoney2(detalle.total)}</p>
                  </div>
                  </div>
                </div>
              </div>
            </>
          )}
        </DialogContent>
      </Dialog>

      <Dialog open={openXml} onOpenChange={setOpenXml}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Cargar CFDI desde XML</DialogTitle>
            <DialogDescription>
              Sube los XML timbrados (o un ZIP con varios) tal como los entrega el SAT o el PAC. Se clasifican como emitidos/recibidos por el RFC de la empresa, se ligan los complementos de pago a sus facturas PPD y se corre el motor de validación. Los repetidos y los que no son de la empresa se omiten.
            </DialogDescription>
          </DialogHeader>
          {resXml ? (
            <div className="space-y-2 text-sm">
              <p><strong>{resXml.nuevos}</strong> CFDI nuevos · {resXml.duplicados} ya existían · {resXml.ajenos} de otra empresa · {resXml.alertas} alertas generadas.</p>
              {resXml.errores.length > 0 && (
                <div className="max-h-48 overflow-auto rounded-md border p-2 text-xs">
                  {resXml.errores.map((e, i) => <p key={i}><span className="font-mono">{e.archivo}</span>: {e.error}</p>)}
                </div>
              )}
              <DialogFooter><Button onClick={() => setOpenXml(false)}>Cerrar</Button></DialogFooter>
            </div>
          ) : (
            <div className="space-y-3">
              <Input type="file" multiple accept=".xml,.zip,application/xml,text/xml,application/zip" onChange={(e) => setArchivosXml(e.target.files)} />
              {errorXml && <p className="text-sm text-destructive">{errorXml}</p>}
              <DialogFooter>
                <Button variant="outline" onClick={() => setOpenXml(false)}>Cancelar</Button>
                <Button onClick={cargarXml} disabled={cargandoXml}>{cargandoXml ? "Cargando…" : "Cargar"}</Button>
              </DialogFooter>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}

function Dato({ k, v }: { k: string; v: string }) {
  return (
    <div>
      <p className="text-xs text-muted-foreground">{k}</p>
      <p>{v}</p>
    </div>
  );
}

function TarjetaTipo({
  titulo,
  r,
  activa,
  onClick,
  extra,
  sinIva,
}: {
  titulo: string;
  r: CfdiResumen["ingreso"];
  activa: boolean;
  onClick: () => void;
  extra: string;
  sinIva?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "rounded-lg border bg-card p-4 text-left transition-colors hover:bg-accent/40",
        activa && "border-primary ring-1 ring-primary",
      )}
    >
      <div className="flex items-center justify-between">
        <p className="text-sm font-medium">{titulo}</p>
        <span className="text-xs text-muted-foreground">{extra}</span>
      </div>
      <p className="mt-1 text-2xl font-semibold tabular-nums">{formatMoney(r.total)}</p>
      <p className="text-xs text-muted-foreground">
        {r.cantidad} CFDI{r.cantidad === 1 ? "" : "s"}
        {!sinIva && ` · subtotal ${formatMoney(r.subtotal)} · IVA ${formatMoney(r.iva)}`}
        {r.ppd > 0 && ` · ${r.ppd} PPD`}
        {r.cancelados > 0 && ` · ${r.cancelados} cancelado${r.cancelados === 1 ? "" : "s"}`}
      </p>
    </button>
  );
}
