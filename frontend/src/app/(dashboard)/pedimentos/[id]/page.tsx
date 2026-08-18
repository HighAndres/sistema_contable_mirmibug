"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft, Download, PackageCheck, Plus, Save, Trash2, X } from "lucide-react";

import { useEmpresa } from "@/components/empresa-provider";
import { StatTile } from "@/components/stat-tile";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ApiError, apiFetch } from "@/lib/api";
import { exportarExcel } from "@/lib/export-xlsx";
import { formatDate, formatMoney2, formatNumber, formatUnit } from "@/lib/format";
import { PERM, can } from "@/lib/permissions";
import type {
  Almacen,
  AplicarInventarioResponse,
  GastoAdicional,
  MetodoProrrateo,
  PedimentoDetalle,
  PedimentoPartida,
  Producto,
} from "@/lib/types";

const METODOS: { value: MetodoProrrateo; label: string; hint: string }[] = [
  { value: "partes_iguales", label: "Partes iguales", hint: "Monto ÷ número de partidas (como el papel de trabajo)" },
  { value: "valor_aduana", label: "Por valor en aduana", hint: "Proporcional al valor de cada partida" },
  { value: "cantidad", label: "Por cantidad", hint: "Proporcional a las piezas de cada partida" },
  { value: "peso", label: "Por peso", hint: "Proporcional a la UMT (kg) declarada" },
];

const SIN_PRODUCTO = "__sin__";

export default function PedimentoDetallePage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { empresaActiva } = useEmpresa();

  const [ped, setPed] = useState<PedimentoDetalle | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // --- configuración del costeo (borrador local hasta "Guardar") ---
  const [gastos, setGastos] = useState<GastoAdicional[]>([]);
  const [utilidad, setUtilidad] = useState("0");
  const [dta, setDta] = useState("0");
  const [metodo, setMetodo] = useState<MetodoProrrateo>("partes_iguales");
  const [referencia, setReferencia] = useState("");
  const [guardando, setGuardando] = useState(false);
  const [errorConfig, setErrorConfig] = useState<string | null>(null);

  // --- edición de partida (clave SAT / producto) ---
  const [productos, setProductos] = useState<Producto[]>([]);
  const [partidaEdit, setPartidaEdit] = useState<PedimentoPartida | null>(null);
  const [editClave, setEditClave] = useState("");
  const [editProducto, setEditProducto] = useState(SIN_PRODUCTO);
  const [guardandoPartida, setGuardandoPartida] = useState(false);
  const [errorPartida, setErrorPartida] = useState<string | null>(null);

  // --- aplicar a inventario ---
  const [almacenes, setAlmacenes] = useState<Almacen[]>([]);
  const [openAplicar, setOpenAplicar] = useState(false);
  const [codigoAlmacen, setCodigoAlmacen] = useState("");
  const [aplicando, setAplicando] = useState(false);
  const [errorAplicar, setErrorAplicar] = useState<string | null>(null);
  const [resultadoAplicar, setResultadoAplicar] = useState<AplicarInventarioResponse | null>(null);

  const [openEliminar, setOpenEliminar] = useState(false);

  const sincronizarForm = useCallback((p: PedimentoDetalle) => {
    setGastos(p.gastos_adicionales);
    setUtilidad(String(p.utilidad));
    setDta(String(p.dta));
    setMetodo(p.metodo_prorrateo);
    setReferencia(p.referencia ?? "");
  }, []);

  const cargar = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [p, alm, prods] = await Promise.all([
        apiFetch<PedimentoDetalle>(`/pedimentos/${id}`),
        apiFetch<Almacen[]>("/inventory/almacenes").catch(() => [] as Almacen[]),
        apiFetch<Producto[]>("/inventory/productos").catch(() => [] as Producto[]),
      ]);
      setPed(p);
      sincronizarForm(p);
      setAlmacenes(alm);
      setProductos(prods);
      if (alm.length > 0 && !codigoAlmacen) setCodigoAlmacen(alm[0].codigo);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "No se pudo cargar el pedimento");
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, sincronizarForm]);

  useEffect(() => {
    if (empresaActiva) void cargar();
  }, [empresaActiva, cargar]);

  const puedeGestionar = !!empresaActiva && can(empresaActiva.permisos, PERM.PEDIMENTOS_GESTIONAR);
  const puedeAjustarInv = !!empresaActiva && can(empresaActiva.permisos, PERM.INVENTARIO_AJUSTAR);
  const editable = !!ped && ped.estatus === "borrador" && puedeGestionar;

  const totalGastos = gastos.reduce((acc, g) => acc + (Number(g.monto) || 0), 0);
  const configCambio =
    !!ped &&
    (Number(utilidad) !== ped.utilidad ||
      Number(dta) !== ped.dta ||
      metodo !== ped.metodo_prorrateo ||
      (referencia || null) !== (ped.referencia || null) ||
      JSON.stringify(gastos) !== JSON.stringify(ped.gastos_adicionales));

  async function guardarConfig() {
    if (!ped) return;
    setErrorConfig(null);
    setGuardando(true);
    try {
      const actualizado = await apiFetch<PedimentoDetalle>(`/pedimentos/${ped.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          referencia: referencia.trim() || null,
          dta: Number(dta) || 0,
          utilidad: Number(utilidad) || 0,
          metodo_prorrateo: metodo,
          gastos_adicionales: gastos
            .filter((g) => g.concepto.trim())
            .map((g) => ({ concepto: g.concepto.trim(), monto: Number(g.monto) || 0 })),
        }),
      });
      setPed(actualizado);
      sincronizarForm(actualizado);
    } catch (err) {
      setErrorConfig(err instanceof ApiError ? err.message : "Error al guardar la configuración");
    } finally {
      setGuardando(false);
    }
  }

  function abrirEdicionPartida(p: PedimentoPartida) {
    setPartidaEdit(p);
    setEditClave(p.clave_prodserv ?? "");
    setEditProducto(p.producto_id ?? SIN_PRODUCTO);
    setErrorPartida(null);
  }

  async function guardarPartida() {
    if (!ped || !partidaEdit) return;
    setGuardandoPartida(true);
    setErrorPartida(null);
    try {
      await apiFetch(`/pedimentos/${ped.id}/partidas/${partidaEdit.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          clave_prodserv: editClave.trim() || null,
          producto_id: editProducto === SIN_PRODUCTO ? null : editProducto,
        }),
      });
      setPartidaEdit(null);
      await cargar();
    } catch (err) {
      setErrorPartida(err instanceof ApiError ? err.message : "Error al guardar la partida");
    } finally {
      setGuardandoPartida(false);
    }
  }

  async function aplicar() {
    if (!ped) return;
    setAplicando(true);
    setErrorAplicar(null);
    try {
      const res = await apiFetch<AplicarInventarioResponse>(`/pedimentos/${ped.id}/aplicar-inventario`, {
        method: "POST",
        body: JSON.stringify({ codigo_almacen: codigoAlmacen, crear_productos_faltantes: true }),
      });
      setResultadoAplicar(res);
      await cargar();
    } catch (err) {
      setErrorAplicar(err instanceof ApiError ? err.message : "Error al aplicar al inventario");
    } finally {
      setAplicando(false);
    }
  }

  async function aplicarClaves() {
    if (!ped) return;
    try {
      const actualizado = await apiFetch<PedimentoDetalle>(`/pedimentos/${ped.id}/aplicar-claves`, { method: "POST" });
      setPed(actualizado);
      sincronizarForm(actualizado);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "No se pudieron aplicar las claves");
    }
  }

  async function eliminar() {
    if (!ped) return;
    try {
      await apiFetch(`/pedimentos/${ped.id}`, { method: "DELETE" });
      router.push("/pedimentos");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "No se pudo eliminar");
      setOpenEliminar(false);
    }
  }

  function exportar() {
    if (!ped) return;
    const costeo = ped.partidas.map((p) => ({
      Pedimento: ped.numero_completo,
      Referencia: ped.referencia ?? "",
      Partida: p.secuencia,
      Fracción: p.fraccion,
      Descripción: p.descripcion,
      "Clave SAT": p.clave_prodserv ?? "",
      "Cantidad UMC": p.cantidad_umc,
      UMC: p.umc_descripcion ?? p.umc_clave,
      "Clave unidad SAT": p.clave_unidad_sat ?? "",
      "Costo unitario MXN": p.precio_unitario,
      "Valor MXN": p.valor_comercial,
      "T.C.": ped.tipo_cambio,
      USD: p.valor_usd,
      IGI: p.igi,
      "IVA importación": p.iva,
      "DTA pedimento": ped.dta,
      "No. partidas": ped.num_partidas,
      "DTA asignado": p.costeo.dta_asignado,
      "DTA por pza": p.costeo.dta_pza,
      "IGI por pza": p.costeo.igi_pza,
      "Gastos asignados": p.costeo.gastos_asignados,
      "Gastos por pza": p.costeo.gastos_pza,
      "Utilidad asignada": p.costeo.utilidad_asignada,
      "Utilidad por pza": p.costeo.utilidad_pza,
      "Costo unitario landed": p.costeo.costo_unitario,
      "Precio unitario venta": p.costeo.precio_unitario_venta,
      Subtotal: p.costeo.subtotal,
      "IVA 16%": p.costeo.iva_16,
      Total: p.costeo.total,
      "Dif. IVA": p.costeo.dif_iva,
    }));
    const prefactura = ped.partidas.map((p) => ({
      Cantidad: p.cantidad_umc,
      "Clave unidad": p.clave_unidad_sat ?? "",
      "Clave prod/serv": p.clave_prodserv ?? "",
      Concepto: p.descripcion,
      "Valor unitario": p.costeo.precio_unitario_venta,
      Importe: p.costeo.subtotal,
      IVA: p.costeo.iva_16,
      Total: p.costeo.total,
    }));
    exportarExcel(`pedimento_${ped.numero_completo.replace(/\s+/g, "_")}`, {
      Costeo: costeo,
      Prefactura: prefactura,
    });
  }

  if (!empresaActiva) return null;
  if (loading && !ped) return <p className="text-sm text-muted-foreground">Cargando…</p>;
  if (error && !ped) {
    return (
      <div className="space-y-3">
        <p className="text-sm text-destructive">{error}</p>
        <Button asChild variant="outline">
          <Link href="/pedimentos">Volver</Link>
        </Button>
      </div>
    );
  }
  if (!ped) return null;

  const r = ped.resumen;
  const sinProducto = ped.partidas.filter((p) => !p.producto_id).length;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1">
          <Button asChild variant="ghost" size="sm" className="-ml-2 h-7 px-2 text-muted-foreground">
            <Link href="/pedimentos">
              <ArrowLeft className="mr-1 h-4 w-4" /> Pedimentos
            </Link>
          </Button>
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="font-mono text-2xl font-semibold">{ped.numero_completo}</h1>
            <Badge variant={ped.estatus === "aplicado" ? "success" : "secondary"}>
              {ped.estatus === "aplicado" ? "Aplicado a inventario" : "Borrador"}
            </Badge>
            <Badge variant="outline">{ped.origen === "m3" ? "Importado de M3" : "Captura manual"}</Badge>
            {ped.clave_pedimento && <Badge variant="outline">Clave {ped.clave_pedimento}</Badge>}
          </div>
          <p className="text-sm text-muted-foreground">
            {ped.proveedor_nombre ?? "Proveedor no especificado"}
            {ped.incoterm ? ` · ${ped.incoterm}` : ""}
            {ped.fecha_pago ? ` · Pagado ${formatDate(ped.fecha_pago)}` : ""}
            {ped.contenedores?.length ? ` · Contenedor ${ped.contenedores.join(", ")}` : ""}
            {ped.archivo_nombre ? ` · ${ped.archivo_nombre}` : ""}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" onClick={exportar}>
            <Download className="mr-2 h-4 w-4" />
            Exportar costeo y prefactura
          </Button>
          {editable && puedeAjustarInv && (
            <Button
              onClick={() => {
                setResultadoAplicar(null);
                setErrorAplicar(null);
                setOpenAplicar(true);
              }}
            >
              <PackageCheck className="mr-2 h-4 w-4" />
              Aplicar al inventario
            </Button>
          )}
          {editable && (
            <Button variant="outline" size="icon" aria-label="Eliminar pedimento" onClick={() => setOpenEliminar(true)}>
              <Trash2 className="h-4 w-4" />
            </Button>
          )}
        </div>
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-6">
        <StatTile label="Tipo de cambio" value={formatNumber(ped.tipo_cambio)} hint={`USD ${formatNumber(ped.valor_usd_total)}`} />
        <StatTile label="Valor en aduana" value={formatMoney2(ped.valor_aduana_total)} hint={`${ped.num_partidas} partidas`} />
        <StatTile label="DTA" value={formatMoney2(r.dta)} hint={ped.otras_contribuciones ? Object.entries(ped.otras_contribuciones).map(([k, v]) => `${k} ${v}`).join(" · ") : undefined} />
        <StatTile label="IGI total" value={formatMoney2(r.igi_total)} />
        <StatTile label="IVA de importación" value={formatMoney2(r.iva_importacion_total)} />
        <StatTile label="Costo total (landed)" value={formatMoney2(r.costo_total)} tone="good" hint={`Refactura ${formatMoney2(r.total_venta)}`} />
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader className="pb-3">
            <CardTitle className="text-base">Configuración del costeo</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <div className="space-y-1.5">
                <Label htmlFor="referencia">Referencia interna</Label>
                <Input id="referencia" value={referencia} onChange={(e) => setReferencia(e.target.value)} disabled={!editable} placeholder="LMA26-019" />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="dta">DTA del pedimento</Label>
                <Input id="dta" type="number" step="0.01" min="0" value={dta} onChange={(e) => setDta(e.target.value)} disabled={!editable} />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="utilidad">Utilidad (monto por pedimento)</Label>
                <Input id="utilidad" type="number" step="0.01" min="0" value={utilidad} onChange={(e) => setUtilidad(e.target.value)} disabled={!editable} />
              </div>
              <div className="space-y-1.5">
                <Label>Método de prorrateo</Label>
                <Select value={metodo} onValueChange={(v) => setMetodo(v as MetodoProrrateo)} disabled={!editable}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {METODOS.map((m) => (
                      <SelectItem key={m.value} value={m.value}>
                        {m.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <p className="text-xs text-muted-foreground">{METODOS.find((m) => m.value === metodo)?.hint}</p>
              </div>
            </div>

            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <Label>Gastos adicionales (fletes, seguros, maniobras, honorarios…)</Label>
                {editable && (
                  <Button type="button" variant="outline" size="sm" onClick={() => setGastos((g) => [...g, { concepto: "", monto: 0 }])}>
                    <Plus className="mr-1 h-3.5 w-3.5" /> Agregar gasto
                  </Button>
                )}
              </div>
              {gastos.length === 0 ? (
                <p className="text-sm text-muted-foreground">Sin gastos adicionales. Solo se prorratean cuando existen.</p>
              ) : (
                <div className="space-y-2">
                  {gastos.map((g, i) => (
                    <div key={i} className="flex gap-2">
                      <Input
                        placeholder="Concepto"
                        value={g.concepto}
                        disabled={!editable}
                        onChange={(e) => setGastos((prev) => prev.map((x, j) => (j === i ? { ...x, concepto: e.target.value } : x)))}
                      />
                      <Input
                        type="number"
                        step="0.01"
                        min="0"
                        className="w-40"
                        value={g.monto}
                        disabled={!editable}
                        onChange={(e) => setGastos((prev) => prev.map((x, j) => (j === i ? { ...x, monto: Number(e.target.value) } : x)))}
                      />
                      {editable && (
                        <Button type="button" variant="ghost" size="icon" aria-label="Quitar gasto" onClick={() => setGastos((prev) => prev.filter((_, j) => j !== i))}>
                          <X className="h-4 w-4" />
                        </Button>
                      )}
                    </div>
                  ))}
                  <p className="text-right text-sm text-muted-foreground">Total gastos: {formatMoney2(totalGastos)}</p>
                </div>
              )}
            </div>

            {errorConfig && <p className="text-sm text-destructive">{errorConfig}</p>}
            {editable && (
              <div className="flex justify-end gap-2">
                <Button variant="outline" onClick={() => sincronizarForm(ped)} disabled={!configCambio || guardando}>
                  Descartar
                </Button>
                <Button onClick={guardarConfig} disabled={!configCambio || guardando}>
                  <Save className="mr-2 h-4 w-4" />
                  {guardando ? "Guardando…" : "Guardar y recalcular"}
                </Button>
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">Resumen de la refactura</CardTitle>
          </CardHeader>
          <CardContent>
            <dl className="space-y-1.5 text-sm">
              <Fila k="Costo mercancía + impuestos + gastos" v={formatMoney2(r.costo_total)} />
              <Fila k="Utilidad" v={formatMoney2(r.utilidad)} />
              <Fila k="Subtotal a facturar" v={formatMoney2(r.subtotal_venta)} strong />
              <Fila k="IVA 16%" v={formatMoney2(r.iva_venta)} />
              <Fila k="Total a facturar" v={formatMoney2(r.total_venta)} strong />
              <Fila
                k="Dif. IVA facturado − IVA importación"
                v={formatMoney2(r.dif_iva_total)}
                tone={r.dif_iva_total < 0 ? "critical" : "good"}
              />
            </dl>
            {sinProducto > 0 && (
              <p className="mt-3 rounded-md border border-amber-500/40 bg-amber-500/10 p-2 text-xs">
                {sinProducto} partida{sinProducto > 1 ? "s" : ""} sin producto del catálogo: se crear
                {sinProducto > 1 ? "án" : "á"} automáticamente al aplicar (o asígnalo desde la tabla).
              </p>
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardContent className="p-0">
          <Tabs defaultValue="costeo">
            <div className="flex flex-wrap items-center justify-between gap-2 border-b px-4 pt-3">
              <TabsList>
                <TabsTrigger value="costeo">Costeo por partida</TabsTrigger>
                <TabsTrigger value="prefactura">Prefactura al cliente</TabsTrigger>
                <TabsTrigger value="datos">Datos del pedimento</TabsTrigger>
              </TabsList>
              {editable && (
                <div className="flex items-center gap-2 pb-2">
                  {ped.partidas.some((p) => !p.clave_prodserv) && (
                    <Button size="sm" variant="outline" onClick={aplicarClaves}>Aplicar claves del catálogo</Button>
                  )}
                  <p className="text-xs text-muted-foreground">Clic en una partida para asignar clave SAT o producto.</p>
                </div>
              )}
            </div>

            <TabsContent value="costeo" className="m-0">
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>#</TableHead>
                      <TableHead>Descripción</TableHead>
                      <TableHead>Fracción</TableHead>
                      <TableHead className="text-right">Cantidad</TableHead>
                      <TableHead>UMC</TableHead>
                      <TableHead className="text-right">Costo unit.</TableHead>
                      <TableHead className="text-right">Valor MXN</TableHead>
                      <TableHead className="text-right">USD</TableHead>
                      <TableHead className="text-right">IGI</TableHead>
                      <TableHead className="text-right">IVA imp.</TableHead>
                      <TableHead className="text-right">DTA/pza</TableHead>
                      <TableHead className="text-right">IGI/pza</TableHead>
                      <TableHead className="text-right">Gastos/pza</TableHead>
                      <TableHead className="text-right">Util./pza</TableHead>
                      <TableHead className="text-right font-semibold">Costo landed</TableHead>
                      <TableHead className="text-right font-semibold">Precio venta</TableHead>
                      <TableHead>Producto</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {ped.partidas.map((p) => (
                      <TableRow key={p.id} className={editable ? "cursor-pointer" : undefined} onClick={editable ? () => abrirEdicionPartida(p) : undefined}>
                        <TableCell className="tabular-nums">{p.secuencia}</TableCell>
                        <TableCell className="max-w-[240px]">
                          <span className="block truncate" title={p.descripcion}>{p.descripcion}</span>
                          {p.clave_prodserv && <span className="text-xs text-muted-foreground">SAT {p.clave_prodserv}</span>}
                        </TableCell>
                        <TableCell className="font-mono text-xs">{p.fraccion}{p.nico ? ` ${p.nico}` : ""}</TableCell>
                        <TableCell className="text-right tabular-nums">{formatNumber(p.cantidad_umc)}</TableCell>
                        <TableCell className="text-xs">{p.umc_descripcion ?? p.umc_clave}{p.clave_unidad_sat ? ` (${p.clave_unidad_sat})` : ""}</TableCell>
                        <TableCell className="text-right tabular-nums">{formatUnit(p.precio_unitario)}</TableCell>
                        <TableCell className="text-right tabular-nums">{formatMoney2(p.valor_comercial)}</TableCell>
                        <TableCell className="text-right tabular-nums">{formatNumber(p.valor_usd)}</TableCell>
                        <TableCell className="text-right tabular-nums">{formatMoney2(p.igi)}</TableCell>
                        <TableCell className="text-right tabular-nums">{formatMoney2(p.iva)}</TableCell>
                        <TableCell className="text-right tabular-nums">{formatUnit(p.costeo.dta_pza)}</TableCell>
                        <TableCell className="text-right tabular-nums">{formatUnit(p.costeo.igi_pza)}</TableCell>
                        <TableCell className="text-right tabular-nums">{formatUnit(p.costeo.gastos_pza)}</TableCell>
                        <TableCell className="text-right tabular-nums">{formatUnit(p.costeo.utilidad_pza)}</TableCell>
                        <TableCell className="text-right font-medium tabular-nums">{formatUnit(p.costeo.costo_unitario)}</TableCell>
                        <TableCell className="text-right font-medium tabular-nums">{formatUnit(p.costeo.precio_unitario_venta)}</TableCell>
                        <TableCell>
                          {p.producto_sku ? (
                            <Badge variant="outline" className="font-mono text-xs">{p.producto_sku}</Badge>
                          ) : (
                            <span className="text-xs text-muted-foreground">nuevo al aplicar</span>
                          )}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </TabsContent>

            <TabsContent value="prefactura" className="m-0">
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="text-right">Cantidad</TableHead>
                      <TableHead>Clave unidad</TableHead>
                      <TableHead>Clave prod/serv</TableHead>
                      <TableHead>Concepto</TableHead>
                      <TableHead className="text-right">Valor unitario</TableHead>
                      <TableHead className="text-right">Importe</TableHead>
                      <TableHead className="text-right">IVA 16%</TableHead>
                      <TableHead className="text-right">Total</TableHead>
                      <TableHead className="text-right">Dif. IVA</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {ped.partidas.map((p) => (
                      <TableRow key={p.id}>
                        <TableCell className="text-right tabular-nums">{formatNumber(p.cantidad_umc)}</TableCell>
                        <TableCell className="font-mono text-xs">{p.clave_unidad_sat ?? "—"}</TableCell>
                        <TableCell className="font-mono text-xs">{p.clave_prodserv ?? <span className="text-amber-600">falta</span>}</TableCell>
                        <TableCell className="max-w-[280px] truncate" title={p.descripcion}>{p.descripcion}</TableCell>
                        <TableCell className="text-right tabular-nums">{formatUnit(p.costeo.precio_unitario_venta)}</TableCell>
                        <TableCell className="text-right tabular-nums">{formatMoney2(p.costeo.subtotal)}</TableCell>
                        <TableCell className="text-right tabular-nums">{formatMoney2(p.costeo.iva_16)}</TableCell>
                        <TableCell className="text-right tabular-nums">{formatMoney2(p.costeo.total)}</TableCell>
                        <TableCell className={`text-right tabular-nums ${p.costeo.dif_iva < 0 ? "text-[color:var(--status-critical)]" : ""}`}>{formatMoney2(p.costeo.dif_iva)}</TableCell>
                      </TableRow>
                    ))}
                    <TableRow className="font-semibold">
                      <TableCell colSpan={5} className="text-right">Totales</TableCell>
                      <TableCell className="text-right tabular-nums">{formatMoney2(r.subtotal_venta)}</TableCell>
                      <TableCell className="text-right tabular-nums">{formatMoney2(r.iva_venta)}</TableCell>
                      <TableCell className="text-right tabular-nums">{formatMoney2(r.total_venta)}</TableCell>
                      <TableCell className="text-right tabular-nums">{formatMoney2(r.dif_iva_total)}</TableCell>
                    </TableRow>
                  </TableBody>
                </Table>
              </div>
            </TabsContent>

            <TabsContent value="datos" className="m-0 p-4">
              <dl className="grid gap-x-8 gap-y-2 text-sm sm:grid-cols-2 lg:grid-cols-3">
                <Fila k="Número" v={ped.numero} mono />
                <Fila k="Patente" v={ped.patente} mono />
                <Fila k="Aduana / sección" v={ped.aduana} mono />
                <Fila k="Clave" v={ped.clave_pedimento ?? "—"} />
                <Fila k="Tipo de operación" v={ped.tipo_operacion === "1" ? "Importación" : ped.tipo_operacion === "2" ? "Exportación" : (ped.tipo_operacion ?? "—")} />
                <Fila k="RFC importador" v={ped.rfc_importador ?? "—"} mono />
                <Fila k="Fecha de entrada" v={ped.fecha_entrada ? formatDate(ped.fecha_entrada) : "—"} />
                <Fila k="Fecha de pago" v={ped.fecha_pago ? formatDate(ped.fecha_pago) : "—"} />
                <Fila k="Peso bruto (kg)" v={ped.peso_bruto != null ? formatNumber(ped.peso_bruto) : "—"} />
                <Fila k="Proveedor" v={ped.proveedor_nombre ?? "—"} />
                <Fila k="ID fiscal proveedor" v={ped.proveedor_id_fiscal ?? "—"} mono />
                <Fila k="Incoterm" v={ped.incoterm ?? "—"} />
                <Fila k="Contenedores" v={ped.contenedores?.join(", ") || "—"} mono />
                <Fila k="Guías" v={ped.guias?.join(", ") || "—"} mono />
                <Fila k="Otras contribuciones" v={ped.otras_contribuciones ? Object.entries(ped.otras_contribuciones).map(([k, v]) => `${k}: ${v}`).join(" · ") : "—"} />
                <Fila k="Archivo" v={ped.archivo_nombre ?? "—"} mono />
                <Fila k="Notas" v={ped.notas ?? "—"} />
              </dl>
            </TabsContent>
          </Tabs>
        </CardContent>
      </Card>

      {/* Editar partida */}
      <Dialog open={!!partidaEdit} onOpenChange={(o) => !o && setPartidaEdit(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Partida {partidaEdit?.secuencia} · {partidaEdit?.descripcion}</DialogTitle>
            <DialogDescription>Clave SAT para facturar y producto del catálogo al que entra esta partida.</DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="clave">Clave prod/serv SAT (c_ClaveProdServ)</Label>
              <Input id="clave" value={editClave} onChange={(e) => setEditClave(e.target.value)} placeholder="p. ej. 26111700" />
            </div>
            <div className="space-y-1.5">
              <Label>Producto del catálogo</Label>
              <Select value={editProducto} onValueChange={setEditProducto}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={SIN_PRODUCTO}>Crear producto nuevo al aplicar</SelectItem>
                  {productos.filter((p) => p.tipo === "producto").map((p) => (
                    <SelectItem key={p.id} value={p.id}>
                      {p.sku} · {p.nombre}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            {errorPartida && <p className="text-sm text-destructive">{errorPartida}</p>}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setPartidaEdit(null)}>Cancelar</Button>
            <Button onClick={guardarPartida} disabled={guardandoPartida}>{guardandoPartida ? "Guardando…" : "Guardar"}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Aplicar al inventario */}
      <Dialog open={openAplicar} onOpenChange={setOpenAplicar}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Aplicar al inventario</DialogTitle>
            <DialogDescription>
              Se registra una entrada por partida con su costo unitario landed ({formatMoney2(r.costo_total)} en total).
              El pedimento queda congelado y ya no se puede modificar.
            </DialogDescription>
          </DialogHeader>
          {resultadoAplicar ? (
            <div className="space-y-3 text-sm">
              <p>
                Listo: <strong>{resultadoAplicar.movimientos_creados}</strong> entradas al inventario,{" "}
                <strong>{resultadoAplicar.productos_creados}</strong> productos nuevos, costo total{" "}
                <strong>{formatMoney2(resultadoAplicar.costo_total)}</strong>.
              </p>
              <DialogFooter>
                <Button variant="outline" onClick={() => setOpenAplicar(false)}>Cerrar</Button>
                <Button asChild><Link href="/inventario">Ver inventario</Link></Button>
              </DialogFooter>
            </div>
          ) : (
            <div className="space-y-4">
              {almacenes.length === 0 ? (
                <p className="text-sm text-destructive">No hay almacenes. Crea uno en Inventario antes de aplicar.</p>
              ) : (
                <div className="space-y-1.5">
                  <Label>Almacén destino</Label>
                  <Select value={codigoAlmacen} onValueChange={setCodigoAlmacen}>
                    <SelectTrigger><SelectValue placeholder="Selecciona un almacén" /></SelectTrigger>
                    <SelectContent>
                      {almacenes.map((a) => (
                        <SelectItem key={a.id} value={a.codigo}>{a.codigo} · {a.nombre}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              )}
              {sinProducto > 0 && (
                <p className="text-sm text-muted-foreground">
                  {sinProducto} partida{sinProducto > 1 ? "s" : ""} sin producto: se crear{sinProducto > 1 ? "án" : "á"} en la
                  categoría &quot;Importación&quot; con SKU derivado de la descripción.
                </p>
              )}
              {errorAplicar && <p className="text-sm text-destructive">{errorAplicar}</p>}
              <DialogFooter>
                <Button variant="outline" onClick={() => setOpenAplicar(false)}>Cancelar</Button>
                <Button onClick={aplicar} disabled={aplicando || !codigoAlmacen}>{aplicando ? "Aplicando…" : "Aplicar"}</Button>
              </DialogFooter>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Eliminar */}
      <Dialog open={openEliminar} onOpenChange={setOpenEliminar}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Eliminar pedimento</DialogTitle>
            <DialogDescription>Se elimina el borrador {ped.numero_completo} con sus {ped.num_partidas} partidas. Esta acción no se puede deshacer.</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpenEliminar(false)}>Cancelar</Button>
            <Button variant="destructive" onClick={eliminar}>Eliminar</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function Fila({ k, v, strong, mono, tone }: { k: string; v: string; strong?: boolean; mono?: boolean; tone?: "good" | "critical" }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <dt className="text-muted-foreground">{k}</dt>
      <dd
        className={[
          "text-right tabular-nums",
          strong ? "font-semibold" : "",
          mono ? "font-mono text-xs" : "",
          tone === "good" ? "text-[color:var(--status-good)]" : "",
          tone === "critical" ? "text-[color:var(--status-critical)]" : "",
        ].join(" ")}
      >
        {v}
      </dd>
    </div>
  );
}
