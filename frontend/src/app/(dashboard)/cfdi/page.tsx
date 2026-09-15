"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { CheckCircle2, Download, FileCode2, FileSpreadsheet, FileUp, RefreshCw, Search, SlidersHorizontal, Tags, Undo2, X } from "lucide-react";

import { useEmpresa } from "@/components/empresa-provider";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ApiError, apiDownload, apiFetch } from "@/lib/api";
import { exportarExcel } from "@/lib/export-xlsx";
import { formatDate, formatMoney, formatMoney2 } from "@/lib/format";
import { PERM, can } from "@/lib/permissions";
import { cn } from "@/lib/utils";
import { CLASIFICACIONES } from "@/lib/types";
import type {
  CargaXmlResponse,
  Catalogo,
  Cfdi,
  CfdiDetalle,
  CfdiEstatus,
  CfdiPage,
  CfdiResumen,
  CfdiTipo,
  Clasificacion,
  ClasificacionMasivaResultado,
  EstadoPago,
  ValoresClasificacion,
} from "@/lib/types";

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
const PAGO_LABEL: Record<EstadoPago, string> = { pagada: "Pagada", parcial: "Parcial", pendiente: "Pendiente" };
const PAGO_VARIANT: Record<EstadoPago, "success" | "warning" | "destructive"> = { pagada: "success", parcial: "warning", pendiente: "destructive" };
const TIPO_LABEL: Record<CfdiTipo, string> = { ingreso: "Ingreso", egreso: "Gasto", pago: "Pago", nomina: "Nómina", nota_credito: "Nota de crédito" };
const CLASIF_LABEL: Record<Clasificacion, string> = Object.fromEntries(CLASIFICACIONES.map((c) => [c.valor, c.etiqueta])) as Record<Clasificacion, string>;
const CLASIF_VARIANT: Record<Clasificacion, "success" | "destructive" | "warning"> = {
  deducible: "success",
  no_deducible: "destructive",
  deduccion_personal: "warning",
};
/** Solo estos tipos se clasifican: un REP no es un gasto y la nómina se deduce por su propia vía. */
const CLASIFICABLES: CfdiTipo[] = ["ingreso", "egreso", "nota_credito"];
const esClasificable = (c: Cfdi) => CLASIFICABLES.includes(c.tipo);

const CLASIFICACION_VACIA = { clasificacion: "" as Clasificacion | "", concepto: "", cuenta_contable: "", referencia_bancaria: "" };
type FormClasificacion = typeof CLASIFICACION_VACIA;

interface Filtros {
  estatus: string;
  emisor: string;
  receptor: string;
  anio: string;
  mes: string;
  metodo: string;
  forma: string;
  q: string;
  estadoPago: string;
  clasificacion: string;
  concepto: string;
}

const FILTROS_VACIOS: Filtros = {
  estatus: TODOS,
  emisor: "",
  receptor: "",
  anio: TODOS,
  mes: TODOS,
  metodo: TODOS,
  forma: TODOS,
  q: "",
  estadoPago: TODOS,
  clasificacion: TODOS,
  concepto: "",
};
const PAGE_SIZE = 100;

export default function CfdiPageRoute() {
  const { empresaActiva } = useEmpresa();
  const [tab, setTab] = useState<TabTipo>("ingreso");
  const [filtros, setFiltros] = useState<Filtros>(FILTROS_VACIOS);
  const [aplicados, setAplicados] = useState<Filtros>(FILTROS_VACIOS);
  const [offset, setOffset] = useState(0);
  const [masFiltros, setMasFiltros] = useState(false);
  const [page, setPage] = useState<CfdiPage | null>(null);
  const [resumen, setResumen] = useState<CfdiResumen | null>(null);
  const [formasPago, setFormasPago] = useState<Catalogo[]>([]);
  const [loading, setLoading] = useState(true);
  const [sincronizando, setSincronizando] = useState(false);
  const [detalle, setDetalle] = useState<CfdiDetalle | null>(null);
  const puedeEditar = can(empresaActiva?.permisos, PERM.CFDI_EDITAR);

  // --- pago registrado a mano (factura PPD sin REP ni movimiento bancario) ---
  const [openPago, setOpenPago] = useState(false);
  const [fechaPago, setFechaPago] = useState("");
  const [notaPago, setNotaPago] = useState("");
  const [guardandoPago, setGuardandoPago] = useState(false);
  const [errorPago, setErrorPago] = useState<string | null>(null);

  function abrirPagoManual() {
    setFechaPago(new Date().toISOString().slice(0, 10));
    setNotaPago("");
    setErrorPago(null);
    setOpenPago(true);
  }

  async function guardarPagoManual() {
    if (!detalle) return;
    setGuardandoPago(true);
    setErrorPago(null);
    try {
      await apiFetch(`/cfdi/${detalle.id}/pago-manual`, { method: "POST", body: JSON.stringify({ fecha: fechaPago, nota: notaPago.trim() || null }) });
      setOpenPago(false);
      await Promise.all([verDetalle(detalle.id), cargar()]);
    } catch (err) {
      setErrorPago(err instanceof ApiError ? err.message : "No se pudo registrar el pago");
    } finally {
      setGuardandoPago(false);
    }
  }

  async function quitarPagoManual() {
    if (!detalle) return;
    setGuardandoPago(true);
    try {
      await apiFetch(`/cfdi/${detalle.id}/pago-manual`, { method: "DELETE" });
      await Promise.all([verDetalle(detalle.id), cargar()]);
    } finally {
      setGuardandoPago(false);
    }
  }

  // --- clasificación del papel de trabajo: selección múltiple en la tabla y
  // captura por lote o factura por factura ---
  const [valores, setValores] = useState<ValoresClasificacion | null>(null);
  const [seleccion, setSeleccion] = useState<Set<string>>(new Set());
  const [openClasif, setOpenClasif] = useState(false);
  const [formClasif, setFormClasif] = useState<FormClasificacion>(CLASIFICACION_VACIA);
  const [guardandoClasif, setGuardandoClasif] = useState(false);
  const [errorClasif, setErrorClasif] = useState<string | null>(null);
  // null = lote (lo seleccionado); un CFDI = edición de esa fila.
  const [clasifDe, setClasifDe] = useState<CfdiDetalle | null>(null);

  const cargarValores = useCallback(async () => {
    try {
      setValores(await apiFetch<ValoresClasificacion>("/cfdi/clasificacion/valores"));
    } catch {
      setValores(null);
    }
  }, []);

  function abrirClasificacionLote() {
    setClasifDe(null);
    setFormClasif(CLASIFICACION_VACIA);
    setErrorClasif(null);
    setOpenClasif(true);
  }

  function abrirClasificacionDe(c: CfdiDetalle) {
    setClasifDe(c);
    setFormClasif({
      clasificacion: c.clasificacion ?? "",
      concepto: c.concepto ?? "",
      cuenta_contable: c.cuenta_contable ?? "",
      referencia_bancaria: c.referencia_bancaria ?? "",
    });
    setErrorClasif(null);
    setOpenClasif(true);
  }

  async function guardarClasificacion() {
    setGuardandoClasif(true);
    setErrorClasif(null);
    const limpio = (v: string) => (v.trim() ? v.trim() : null);
    try {
      if (clasifDe) {
        // Edición de una fila: se escribe completa, lo vacío se limpia.
        const actualizado = await apiFetch<Cfdi>(`/cfdi/${clasifDe.id}/clasificacion`, {
          method: "PUT",
          body: JSON.stringify({
            clasificacion: formClasif.clasificacion || null,
            concepto: limpio(formClasif.concepto),
            cuenta_contable: limpio(formClasif.cuenta_contable),
            referencia_bancaria: limpio(formClasif.referencia_bancaria),
          }),
        });
        setDetalle((d) => (d && d.id === actualizado.id ? { ...d, ...actualizado } : d));
      } else {
        // Lote: lo que va vacío NO se toca.
        const res = await apiFetch<ClasificacionMasivaResultado>("/cfdi/clasificacion-masiva", {
          method: "POST",
          body: JSON.stringify({
            cfdi_ids: Array.from(seleccion),
            clasificacion: formClasif.clasificacion || null,
            concepto: limpio(formClasif.concepto),
            cuenta_contable: limpio(formClasif.cuenta_contable),
            referencia_bancaria: limpio(formClasif.referencia_bancaria),
          }),
        });
        if (res.omitidos > 0 && res.actualizados === 0) throw new ApiError(400, "No se pudo clasificar ninguna de las facturas seleccionadas");
        setSeleccion(new Set());
      }
      setOpenClasif(false);
      await Promise.all([cargar(), cargarValores()]);
    } catch (err) {
      setErrorClasif(err instanceof ApiError ? err.message : "Error al guardar la clasificación");
    } finally {
      setGuardandoClasif(false);
    }
  }

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
      if (aplicados.estadoPago !== TODOS) p.set("estado_pago", aplicados.estadoPago);
      if (aplicados.clasificacion !== TODOS) p.set("clasificacion", aplicados.clasificacion);
      if (aplicados.concepto.trim()) p.set("concepto", aplicados.concepto.trim());
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
    apiFetch<Catalogo[]>("/catalogs/forma_pago")
      .then(setFormasPago)
      .catch(() => setFormasPago([]));
    void cargarValores();
  }, [empresaActiva, cargarValores]);

  function aplicarFiltros() {
    setOffset(0);
    setAplicados(filtros);
    setSeleccion(new Set());
  }
  function limpiarFiltros() {
    setMasFiltros(false);
    setFiltros(FILTROS_VACIOS);
    setAplicados(FILTROS_VACIOS);
    setOffset(0);
  }
  function cambiarTab(v: string) {
    setTab(v as TabTipo);
    setOffset(0);
    setSeleccion(new Set());
  }

  function alternarSeleccion(id: string) {
    setSeleccion((prev) => {
      const s = new Set(prev);
      if (s.has(id)) s.delete(id);
      else s.add(id);
      return s;
    });
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
        "Estado de pago":
          c.estado_pago && c.metodo_pago_codigo === "PPD" ? `${PAGO_LABEL[c.estado_pago]}${c.pago_manual_fecha ? ` (a mano ${c.pago_manual_fecha})` : ""}` : "",
        Clasificación: c.clasificacion ? CLASIF_LABEL[c.clasificacion] : "",
        Concepto: c.concepto ?? "",
        "Cuenta contable": c.cuenta_contable ?? "",
        "Referencia bancaria": c.referencia_bancaria ?? "",
      })),
    });
  }

  if (!empresaActiva) return null;
  const permisos = empresaActiva.permisos;
  const hayFiltros = JSON.stringify(aplicados) !== JSON.stringify(FILTROS_VACIOS);
  const tabActual = TABS.find((t) => t.value === tab)!;
  const anios = resumen?.anios ?? [];
  // Cuántos filtros plegados están puestos, para que no se olviden aplicados.
  const filtrosAvanzadosActivos =
    (["emisor", "receptor", "concepto"] as const).filter((k) => aplicados[k].trim()).length +
    (["estatus", "metodo", "forma", "clasificacion"] as const).filter((k) => aplicados[k] !== TODOS).length;
  const seleccionablesVisibles = (page?.items ?? []).filter(esClasificable);
  const seleccionadasFueraDePantalla = Array.from(seleccion).filter((id) => !(page?.items ?? []).some((c) => c.id === id)).length;
  // Fecha, UUID, serie/folio, emisor, receptor, método, forma, subtotal, total,
  // estatus, pago y clasificación; +1 por la columna "Tipo" y +1 por la casilla.
  const columnas = 12 + (tab === "todos" ? 1 : 0) + (puedeEditar ? 1 : 0);
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
            <Download className="mr-2 h-4 w-4" /> Exportar vista
          </Button>
          {can(permisos, PERM.REPORTES_LEER) && (
            <Button variant="outline" asChild>
              <Link href="/reportes">
                <FileSpreadsheet className="mr-2 h-4 w-4" /> Reportes
              </Link>
            </Button>
          )}
          {can(permisos, PERM.SAT_SINCRONIZAR) && (
            <Button
              variant="outline"
              onClick={() => {
                setArchivosXml(null);
                setResXml(null);
                setErrorXml(null);
                setOpenXml(true);
              }}
            >
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
                <span className="ml-2 rounded-full bg-muted px-2 py-0.5 text-xs tabular-nums text-muted-foreground">{resumen[t.value].cantidad}</span>
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
          <TarjetaTipo
            titulo="Notas de crédito"
            r={resumen.nota_credito}
            activa={tab === "nota_credito"}
            onClick={() => cambiarTab("nota_credito")}
            extra="Tipo E"
          />
        </div>
      )}

      <Card>
        <CardContent className="space-y-3 p-4">
          {/* Lo del día a día a la vista; el resto se pliega para que la barra no
              se coma la pantalla. El contador filtra casi siempre por periodo. */}
          <div className="flex flex-wrap items-center gap-2">
            <div className="relative min-w-[260px] flex-1">
              <Search className="pointer-events-none absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
              <Input
                className="pl-8"
                placeholder="Buscar por UUID, serie/folio, RFC o nombre…"
                value={filtros.q}
                onChange={(e) => setFiltros({ ...filtros, q: e.target.value })}
                onKeyDown={(e) => e.key === "Enter" && aplicarFiltros()}
              />
            </div>
            <Select value={filtros.anio} onValueChange={(v) => setFiltros({ ...filtros, anio: v })}>
              <SelectTrigger className="w-[120px]">
                <SelectValue placeholder="Año" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={TODOS}>Todo año</SelectItem>
                {anios.map((a) => (
                  <SelectItem key={a} value={String(a)}>
                    {a}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select value={filtros.mes} onValueChange={(v) => setFiltros({ ...filtros, mes: v })}>
              <SelectTrigger className="w-[120px]">
                <SelectValue placeholder="Mes" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={TODOS}>Todo mes</SelectItem>
                {MESES.map((m, i) => (
                  <SelectItem key={m} value={String(i + 1)}>
                    {m}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {(tab === "ingreso" || tab === "egreso" || tab === "todos") && (
              <Select value={filtros.estadoPago} onValueChange={(v) => setFiltros({ ...filtros, estadoPago: v })}>
                <SelectTrigger className="w-[190px]">
                  <SelectValue placeholder="Estado de pago" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={TODOS}>Pagadas y pendientes</SelectItem>
                  <SelectItem value="pagada">{tab === "egreso" ? "Pagadas" : "Cobradas / pagadas"}</SelectItem>
                  <SelectItem value="pendiente">Pendientes (PPD sin pagar)</SelectItem>
                </SelectContent>
              </Select>
            )}
            <Button variant="ghost" onClick={() => setMasFiltros((v) => !v)}>
              <SlidersHorizontal className="mr-1 h-4 w-4" />
              {masFiltros ? "Menos filtros" : "Más filtros"}
              {filtrosAvanzadosActivos > 0 && (
                <Badge className="ml-1" variant="secondary">
                  {filtrosAvanzadosActivos}
                </Badge>
              )}
            </Button>
            <div className="ml-auto flex gap-2">
              {hayFiltros && (
                <Button variant="ghost" onClick={limpiarFiltros}>
                  <X className="mr-1 h-4 w-4" /> Limpiar
                </Button>
              )}
              <Button variant="secondary" onClick={aplicarFiltros}>
                Aplicar filtros
              </Button>
            </div>
          </div>

          {masFiltros && (
            <div className="flex flex-wrap items-center gap-2 border-t pt-3">
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
              <Select value={filtros.estatus} onValueChange={(v) => setFiltros({ ...filtros, estatus: v })}>
                <SelectTrigger className="w-[190px]">
                  <SelectValue placeholder="Estatus" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={TODOS}>Todos los estatus</SelectItem>
                  <SelectItem value="vigente">Vigente</SelectItem>
                  <SelectItem value="cancelado">Cancelado</SelectItem>
                  <SelectItem value="en_proceso">En proceso de cancelación</SelectItem>
                </SelectContent>
              </Select>
              <Select value={filtros.metodo} onValueChange={(v) => setFiltros({ ...filtros, metodo: v })}>
                <SelectTrigger className="w-[150px]">
                  <SelectValue placeholder="Método" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={TODOS}>PUE y PPD</SelectItem>
                  <SelectItem value="PUE">PUE · una exhibición</SelectItem>
                  <SelectItem value="PPD">PPD · parcialidades</SelectItem>
                </SelectContent>
              </Select>
              <Select value={filtros.forma} onValueChange={(v) => setFiltros({ ...filtros, forma: v })}>
                <SelectTrigger className="w-[220px]">
                  <SelectValue placeholder="Forma de pago" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={TODOS}>Toda forma de pago</SelectItem>
                  {formasPago.map((f) => (
                    <SelectItem key={f.codigo} value={f.codigo}>
                      {f.codigo} · {f.nombre}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {tab !== "pago" && tab !== "nomina" && (
                <>
                  <Select value={filtros.clasificacion} onValueChange={(v) => setFiltros({ ...filtros, clasificacion: v })}>
                    <SelectTrigger className="w-[190px]">
                      <SelectValue placeholder="Clasificación" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value={TODOS}>Toda clasificación</SelectItem>
                      <SelectItem value="sin_clasificar">Sin clasificar</SelectItem>
                      {CLASIFICACIONES.map((c) => (
                        <SelectItem key={c.valor} value={c.valor}>
                          {c.etiqueta}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <Input
                    placeholder="Concepto"
                    className="w-[150px]"
                    list="conceptos-usados"
                    value={filtros.concepto}
                    onChange={(e) => setFiltros({ ...filtros, concepto: e.target.value })}
                    onKeyDown={(e) => e.key === "Enter" && aplicarFiltros()}
                  />
                </>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      <datalist id="conceptos-usados">
        {(valores?.conceptos ?? []).map((c) => (
          <option key={c} value={c} />
        ))}
      </datalist>
      <datalist id="cuentas-usadas">
        {(valores?.cuentas_contables ?? []).map((c) => (
          <option key={c} value={c} />
        ))}
      </datalist>

      {puedeEditar && seleccion.size > 0 && (
        <div className="flex flex-wrap items-center gap-3 rounded-md border bg-muted/50 px-4 py-2 text-sm">
          <span className="font-medium">{seleccion.size} seleccionada(s)</span>
          {/* La selección se conserva al paginar, a propósito: así se clasifica
              un lote grande de varias páginas. Se avisa para que nadie aplique
              una clasificación creyendo que solo afecta a lo que está viendo. */}
          {seleccionadasFueraDePantalla > 0 && <span className="text-muted-foreground">{seleccionadasFueraDePantalla} de otras páginas</span>}
          <Button size="sm" onClick={abrirClasificacionLote}>
            <Tags className="mr-1 h-4 w-4" /> Clasificar
          </Button>
          <Button size="sm" variant="ghost" onClick={() => setSeleccion(new Set())}>
            Quitar selección
          </Button>
        </div>
      )}

      <Card>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  {puedeEditar && (
                    <TableHead className="w-8">
                      <input
                        type="checkbox"
                        aria-label="Seleccionar todo lo visible"
                        className="h-4 w-4 accent-primary"
                        checked={seleccionablesVisibles.length > 0 && seleccionablesVisibles.every((c) => seleccion.has(c.id))}
                        onChange={(e) =>
                          setSeleccion(
                            e.target.checked
                              ? new Set(Array.from(seleccion).concat(seleccionablesVisibles.map((c) => c.id)))
                              : new Set(Array.from(seleccion).filter((id) => !seleccionablesVisibles.some((c) => c.id === id))),
                          )
                        }
                      />
                    </TableHead>
                  )}
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
                  <TableHead>Pago</TableHead>
                  <TableHead>Clasificación</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {loading && (
                  <TableRow>
                    <TableCell colSpan={columnas} className="py-8 text-center text-muted-foreground">
                      Cargando...
                    </TableCell>
                  </TableRow>
                )}
                {!loading &&
                  page?.items.map((c) => (
                    <TableRow key={c.id} className="cursor-pointer" onClick={() => verDetalle(c.id)}>
                      {puedeEditar && (
                        <TableCell onClick={(e) => e.stopPropagation()}>
                          {esClasificable(c) ? (
                            <input
                              type="checkbox"
                              aria-label={`Seleccionar ${c.uuid_fiscal}`}
                              className="h-4 w-4 accent-primary"
                              checked={seleccion.has(c.id)}
                              onChange={() => alternarSeleccion(c.id)}
                            />
                          ) : null}
                        </TableCell>
                      )}
                      <TableCell className="whitespace-nowrap">{formatDate(c.fecha)}</TableCell>
                      <TableCell className="whitespace-nowrap font-mono text-xs" title={c.uuid_fiscal}>
                        {c.uuid_fiscal.slice(0, 8)}…{c.uuid_fiscal.slice(-4)}
                      </TableCell>
                      <TableCell className="whitespace-nowrap font-mono text-xs">{[c.serie, c.folio].filter(Boolean).join("-") || "—"}</TableCell>
                      {tab === "todos" && <TableCell>{TIPO_LABEL[c.tipo]}</TableCell>}
                      <TableCell className="max-w-56">
                        <span className="block truncate" title={c.nombre_emisor}>
                          {c.nombre_emisor}
                        </span>
                        <span className="font-mono text-xs text-muted-foreground">{c.rfc_emisor}</span>
                      </TableCell>
                      <TableCell className="max-w-56">
                        <span className="block truncate" title={c.nombre_receptor}>
                          {c.nombre_receptor}
                        </span>
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
                      <TableCell>
                        {c.estado_pago && c.metodo_pago_codigo === "PPD" ? (
                          <Badge
                            variant={PAGO_VARIANT[c.estado_pago]}
                            title={c.pago_manual_fecha ? `Registrada a mano el ${formatDate(c.pago_manual_fecha)}` : undefined}
                          >
                            {PAGO_LABEL[c.estado_pago]}
                            {c.pago_manual_fecha ? " · a mano" : ""}
                          </Badge>
                        ) : (
                          <span className="text-muted-foreground">—</span>
                        )}
                      </TableCell>
                      <TableCell className="max-w-44">
                        {c.clasificacion ? (
                          <Badge variant={CLASIF_VARIANT[c.clasificacion]}>{CLASIF_LABEL[c.clasificacion]}</Badge>
                        ) : esClasificable(c) ? (
                          <span className="text-xs text-muted-foreground">Sin clasificar</span>
                        ) : (
                          <span className="text-muted-foreground">—</span>
                        )}
                        {(c.concepto || c.cuenta_contable) && (
                          <span className="block truncate text-xs text-muted-foreground" title={[c.concepto, c.cuenta_contable].filter(Boolean).join(" · ")}>
                            {[c.concepto, c.cuenta_contable].filter(Boolean).join(" · ")}
                          </span>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                {!loading && page?.items.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={columnas} className="py-8 text-center text-muted-foreground">
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
                <Button variant="outline" size="sm" disabled={paginaActual <= 1} onClick={() => setOffset(offset - PAGE_SIZE)}>
                  Anterior
                </Button>
                <span className="self-center">
                  {paginaActual} / {totalPaginas}
                </span>
                <Button variant="outline" size="sm" disabled={paginaActual >= totalPaginas} onClick={() => setOffset(offset + PAGE_SIZE)}>
                  Siguiente
                </Button>
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
                  <Dato
                    k="Método de pago"
                    v={
                      detalle.metodo_pago_codigo
                        ? `${detalle.metodo_pago_codigo} · ${detalle.metodo_pago_codigo === "PUE" ? "una sola exhibición" : "parcialidades o diferido"}`
                        : "—"
                    }
                  />
                  <Dato
                    k="Forma de pago"
                    v={detalle.forma_pago_codigo ? `${detalle.forma_pago_codigo} · ${formaNombre[detalle.forma_pago_codigo] ?? ""}` : "—"}
                  />
                  <Dato k="Uso CFDI" v={detalle.uso_cfdi_codigo ?? "—"} />
                </div>

                {CLASIFICABLES.includes(detalle.tipo) && (
                  <div className="space-y-2 rounded-md border p-3">
                    <div className="flex items-center justify-between gap-2">
                      <p className="font-medium">Clasificación</p>
                      {puedeEditar && (
                        <Button variant="outline" size="sm" className="h-7 text-xs" onClick={() => abrirClasificacionDe(detalle)}>
                          <Tags className="mr-1 h-3 w-3" /> {detalle.clasificacion ? "Editar" : "Clasificar"}
                        </Button>
                      )}
                    </div>
                    {detalle.clasificacion ? (
                      <div className="grid grid-cols-2 gap-x-6 gap-y-1 sm:grid-cols-3">
                        <div>
                          <p className="text-xs text-muted-foreground">Efecto fiscal</p>
                          <Badge variant={CLASIF_VARIANT[detalle.clasificacion]}>{CLASIF_LABEL[detalle.clasificacion]}</Badge>
                        </div>
                        <Dato k="Concepto" v={detalle.concepto ?? "—"} />
                        <Dato k="Cuenta contable" v={detalle.cuenta_contable ?? "—"} />
                        <Dato k="Referencia bancaria" v={detalle.referencia_bancaria ?? "—"} />
                      </div>
                    ) : (
                      <p className="text-xs text-muted-foreground">Sin clasificar: por ahora cuenta como deducible en el ISR y su IVA como acreditable.</p>
                    )}
                  </div>
                )}

                {detalle.metodo_pago_codigo === "PPD" && (
                  <div className="space-y-2 rounded-md border p-3">
                    <div className="flex items-center justify-between">
                      <p className="font-medium">Complementos de pago recibidos</p>
                      <Badge variant={(detalle.saldo_pendiente ?? 0) > 0 ? "warning" : "success"}>
                        {(detalle.saldo_pendiente ?? 0) > 0
                          ? `Saldo pendiente ${formatMoney2(detalle.saldo_pendiente ?? 0)}`
                          : detalle.direccion === "emitido"
                            ? "Cobrada"
                            : "Pagada"}
                      </Badge>
                    </div>
                    {detalle.pago_manual_fecha ? (
                      <div className="flex flex-wrap items-center justify-between gap-2 rounded-md bg-accent px-2 py-1.5 text-xs">
                        <span>
                          <CheckCircle2 className="mr-1 inline h-3.5 w-3.5 text-[color:var(--status-good)]" />
                          Registrada a mano como {detalle.direccion === "emitido" ? "cobrada" : "pagada"} el {formatDate(detalle.pago_manual_fecha)}
                          {detalle.pago_manual_nota && <span className="text-muted-foreground"> · {detalle.pago_manual_nota}</span>}
                        </span>
                        {puedeEditar && (
                          <Button variant="ghost" size="sm" className="h-7 text-xs" disabled={guardandoPago} onClick={quitarPagoManual}>
                            <Undo2 className="mr-1 h-3 w-3" /> Quitar marca
                          </Button>
                        )}
                      </div>
                    ) : (
                      puedeEditar &&
                      detalle.estatus === "vigente" &&
                      (detalle.saldo_pendiente ?? 0) > 0 && (
                        <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
                          <span className="text-muted-foreground">
                            ¿Se {detalle.direccion === "emitido" ? "cobró" : "pagó"} sin REP ni movimiento bancario identificable?
                          </span>
                          <Button variant="outline" size="sm" className="h-7 text-xs" onClick={abrirPagoManual}>
                            <CheckCircle2 className="mr-1 h-3 w-3" /> Marcar como {detalle.direccion === "emitido" ? "cobrada" : "pagada"}
                          </Button>
                        </div>
                      )
                    )}
                    {detalle.pagos_recibidos.length === 0 ? (
                      <p className="text-xs text-muted-foreground">
                        {detalle.pago_manual_fecha
                          ? "Sin REP; cuenta como pagada por la marca manual."
                          : "Ningún REP la paga todavía (cuenta por cobrar / pagar)."}
                      </p>
                    ) : (
                      <ul className="space-y-1 text-xs">
                        {detalle.pagos_recibidos.map((p) => (
                          <li key={p.cfdi_pago_id + p.uuid_relacionado} className="flex justify-between gap-2">
                            <span>
                              Parcialidad {p.num_parcialidad ?? "—"} · {p.fecha_pago ? formatDate(p.fecha_pago) : "—"} ·{" "}
                              <span className="font-mono">{p.uuid_pago.slice(0, 8)}…</span>
                            </span>
                            <span className="tabular-nums">
                              {formatMoney2(p.imp_pagado)}
                              {p.imp_saldo_insoluto != null ? ` · resta ${formatMoney2(p.imp_saldo_insoluto)}` : ""}
                            </span>
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
                          <span>
                            <span className="font-mono">{p.uuid_relacionado}</span> · parcialidad {p.num_parcialidad ?? "—"}
                          </span>
                          <span className="tabular-nums">
                            {formatMoney2(p.imp_pagado)}
                            {p.imp_saldo_insoluto != null ? ` · resta ${formatMoney2(p.imp_saldo_insoluto)}` : ""}
                          </span>
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
                      <Button
                        variant="link"
                        size="sm"
                        className="ml-1 h-auto p-0 text-xs"
                        onClick={() => apiDownload(`/sat/xml/${detalle.id}`, `${detalle.uuid_fiscal}.xml`)}
                      >
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

      <Dialog open={openClasif} onOpenChange={setOpenClasif}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{clasifDe ? "Clasificar factura" : `Clasificar ${seleccion.size} factura(s)`}</DialogTitle>
            <DialogDescription>
              {clasifDe
                ? "Se guarda tal cual: lo que dejes vacío se borra."
                : "Solo se aplica lo que llenes; lo que dejes vacío no se toca en las facturas seleccionadas."}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div className="space-y-1">
              <Label>Efecto fiscal</Label>
              <Select
                value={formClasif.clasificacion || TODOS}
                onValueChange={(v) => setFormClasif({ ...formClasif, clasificacion: v === TODOS ? "" : (v as Clasificacion) })}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Sin cambio" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={TODOS}>{clasifDe ? "Sin clasificar" : "Sin cambio"}</SelectItem>
                  {CLASIFICACIONES.map((c) => (
                    <SelectItem key={c.valor} value={c.valor}>
                      {c.etiqueta} · <span className="text-muted-foreground">{c.ayuda}</span>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label htmlFor="clasif-concepto">Concepto</Label>
              <Input
                id="clasif-concepto"
                list="conceptos-usados"
                placeholder="TELEFONOS, PEAJE, HONORARIOS MEDICOS…"
                value={formClasif.concepto}
                onChange={(e) => setFormClasif({ ...formClasif, concepto: e.target.value })}
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label htmlFor="clasif-cuenta">Cuenta contable</Label>
                <Input
                  id="clasif-cuenta"
                  list="cuentas-usadas"
                  placeholder="6100-039-000"
                  value={formClasif.cuenta_contable}
                  onChange={(e) => setFormClasif({ ...formClasif, cuenta_contable: e.target.value })}
                />
              </div>
              <div className="space-y-1">
                <Label htmlFor="clasif-ref">Referencia bancaria</Label>
                <Input
                  id="clasif-ref"
                  placeholder="ENE 1061"
                  value={formClasif.referencia_bancaria}
                  onChange={(e) => setFormClasif({ ...formClasif, referencia_bancaria: e.target.value })}
                />
              </div>
            </div>
            <p className="text-xs text-muted-foreground">
              Un gasto no deducible o de deducción personal deja de restar en el ISR y su IVA deja de ser acreditable.
            </p>
            {errorClasif && <p className="text-sm text-destructive">{errorClasif}</p>}
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setOpenClasif(false)}>
              Cancelar
            </Button>
            <Button onClick={guardarClasificacion} disabled={guardandoClasif}>
              {guardandoClasif ? "Guardando..." : "Guardar"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={openXml} onOpenChange={setOpenXml}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Cargar CFDI desde XML</DialogTitle>
            <DialogDescription>
              Sube los XML timbrados (o un ZIP con varios) tal como los entrega el SAT o el PAC. Se clasifican como emitidos/recibidos por el RFC de la empresa,
              se ligan los complementos de pago a sus facturas PPD y se corre el motor de validación. Los repetidos y los que no son de la empresa se omiten.
            </DialogDescription>
          </DialogHeader>
          {resXml ? (
            <div className="space-y-2 text-sm">
              <p>
                <strong>{resXml.nuevos}</strong> CFDI nuevos · {resXml.duplicados} ya existían · {resXml.ajenos} de otra empresa · {resXml.alertas} alertas
                generadas.
              </p>
              {resXml.errores.length > 0 && (
                <div className="max-h-48 overflow-auto rounded-md border p-2 text-xs">
                  {resXml.errores.map((e, i) => (
                    <p key={i}>
                      <span className="font-mono">{e.archivo}</span>: {e.error}
                    </p>
                  ))}
                </div>
              )}
              <DialogFooter>
                <Button onClick={() => setOpenXml(false)}>Cerrar</Button>
              </DialogFooter>
            </div>
          ) : (
            <div className="space-y-3">
              <Input type="file" multiple accept=".xml,.zip,application/xml,text/xml,application/zip" onChange={(e) => setArchivosXml(e.target.files)} />
              {errorXml && <p className="text-sm text-destructive">{errorXml}</p>}
              <DialogFooter>
                <Button variant="outline" onClick={() => setOpenXml(false)}>
                  Cancelar
                </Button>
                <Button onClick={cargarXml} disabled={cargandoXml}>
                  {cargandoXml ? "Cargando…" : "Cargar"}
                </Button>
              </DialogFooter>
            </div>
          )}
        </DialogContent>
      </Dialog>

      <Dialog open={openPago} onOpenChange={setOpenPago}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Marcar como {detalle?.direccion === "emitido" ? "cobrada" : "pagada"} a mano</DialogTitle>
            <DialogDescription>
              Factura {[detalle?.serie, detalle?.folio].filter(Boolean).join("-") || detalle?.uuid_fiscal.slice(0, 8)} por {formatMoney2(detalle?.total ?? 0)}.
              Desde la fecha que indiques contará como {detalle?.direccion === "emitido" ? "cobrada" : "pagada"} en IVA, ISR, saldos y reportes, aunque no
              exista complemento de pago ni movimiento bancario. Queda registrado en la bitácora.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="fecha-pago">Fecha de {detalle?.direccion === "emitido" ? "cobro" : "pago"}</Label>
              <Input id="fecha-pago" type="date" value={fechaPago} min={detalle?.fecha} onChange={(e) => setFechaPago(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="nota-pago">Nota (opcional)</Label>
              <Input
                id="nota-pago"
                maxLength={255}
                placeholder="p. ej. Depósito del 12/08 sin REP, confirmado con el cliente"
                value={notaPago}
                onChange={(e) => setNotaPago(e.target.value)}
              />
            </div>
            {errorPago && <p className="text-sm text-destructive">{errorPago}</p>}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpenPago(false)}>
              Cancelar
            </Button>
            <Button onClick={guardarPagoManual} disabled={guardandoPago || !fechaPago}>
              {guardandoPago ? "Guardando…" : "Registrar"}
            </Button>
          </DialogFooter>
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
      className={cn("rounded-lg border bg-card p-4 text-left transition-colors hover:bg-accent/40", activa && "border-primary ring-1 ring-primary")}
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
