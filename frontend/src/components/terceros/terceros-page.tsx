"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { AlertTriangle, FileUp, Plus, RefreshCw, Search } from "lucide-react";

import { CargaMasivaDialog } from "@/components/carga-masiva-dialog";
import { useEmpresa } from "@/components/empresa-provider";
import { StatTile } from "@/components/stat-tile";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ApiError, apiFetch } from "@/lib/api";
import { formatDate, formatMoney, formatMoney2 } from "@/lib/format";
import { PERM, can } from "@/lib/permissions";
import type { Cfdi, CfdiPage, Tercero, TerceroDetalle, TerceroTipo } from "@/lib/types";

const TODOS = "__todos__";

interface Props {
  tipo: "cliente" | "proveedor";
}

interface Form {
  rfc: string;
  nombre: string;
  tipo: TerceroTipo;
  email: string;
  telefono: string;
  contacto: string;
  dias_credito: string;
  limite_credito: string;
  codigo_postal: string;
  regimen_fiscal_codigo: string;
  notas: string;
  activo: boolean;
}

const FORM_VACIO = (tipo: TerceroTipo): Form => ({ rfc: "", nombre: "", tipo, email: "", telefono: "", contacto: "", dias_credito: "0", limite_credito: "", codigo_postal: "", regimen_fiscal_codigo: "", notas: "", activo: true });

export function TercerosPage({ tipo }: Props) {
  const { empresaActiva } = useEmpresa();
  const esCliente = tipo === "cliente";
  const titulo = esCliente ? "Clientes" : "Proveedores";
  const [items, setItems] = useState<Tercero[]>([]);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState("");
  const [activo, setActivo] = useState("true");
  const [sincronizando, setSincronizando] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [openCarga, setOpenCarga] = useState(false);

  // alta / edición
  const [openForm, setOpenForm] = useState(false);
  const [editId, setEditId] = useState<string | null>(null);
  const [form, setForm] = useState<Form>(FORM_VACIO(tipo));
  const [guardando, setGuardando] = useState(false);
  const [errorForm, setErrorForm] = useState<string | null>(null);

  // detalle
  const [detalle, setDetalle] = useState<TerceroDetalle | null>(null);
  const [cfdis, setCfdis] = useState<Cfdi[]>([]);

  const puedeGestionar = !!empresaActiva && can(empresaActiva.permisos, PERM.TERCEROS_GESTIONAR);

  const cargar = useCallback(async () => {
    setLoading(true);
    try {
      const p = new URLSearchParams({ tipo });
      if (q.trim()) p.set("q", q.trim());
      if (activo !== TODOS) p.set("activo", activo);
      setItems(await apiFetch<Tercero[]>(`/terceros?${p}`));
    } finally {
      setLoading(false);
    }
  }, [tipo, q, activo]);

  useEffect(() => {
    if (empresaActiva) void cargar();
  }, [empresaActiva, cargar]);

  async function sincronizar() {
    setSincronizando(true);
    setMsg(null);
    try {
      const r = await apiFetch<{ creados: number; actualizados: number; total: number }>("/terceros/sincronizar", { method: "POST" });
      setMsg(`Detectados desde los CFDI: ${r.creados} nuevos, ${r.actualizados} actualizados (${r.total} en total).`);
      await cargar();
    } catch (err) {
      setMsg(err instanceof ApiError ? err.message : "No se pudo sincronizar");
    } finally {
      setSincronizando(false);
    }
  }

  function abrirNuevo() {
    setEditId(null);
    setForm(FORM_VACIO(tipo));
    setErrorForm(null);
    setOpenForm(true);
  }
  function abrirEditar(t: Tercero) {
    setEditId(t.id);
    setForm({
      rfc: t.rfc, nombre: t.nombre, tipo: t.tipo, email: t.email ?? "", telefono: t.telefono ?? "", contacto: t.contacto ?? "",
      dias_credito: String(t.dias_credito), limite_credito: t.limite_credito != null ? String(t.limite_credito) : "",
      codigo_postal: t.codigo_postal ?? "", regimen_fiscal_codigo: t.regimen_fiscal_codigo ?? "", notas: t.notas ?? "", activo: t.activo,
    });
    setErrorForm(null);
    setOpenForm(true);
  }

  async function guardar() {
    setGuardando(true);
    setErrorForm(null);
    const body = {
      nombre: form.nombre.trim(), tipo: form.tipo, email: form.email.trim() || null, telefono: form.telefono.trim() || null, contacto: form.contacto.trim() || null,
      dias_credito: Number(form.dias_credito) || 0, limite_credito: form.limite_credito.trim() === "" ? null : Number(form.limite_credito),
      codigo_postal: form.codigo_postal.trim() || null, regimen_fiscal_codigo: form.regimen_fiscal_codigo.trim() || null, notas: form.notas.trim() || null, activo: form.activo,
    };
    try {
      if (editId) {
        await apiFetch(`/terceros/${editId}`, { method: "PATCH", body: JSON.stringify(body) });
      } else {
        await apiFetch("/terceros", { method: "POST", body: JSON.stringify({ ...body, rfc: form.rfc.trim().toUpperCase() }) });
      }
      setOpenForm(false);
      await cargar();
      if (detalle && editId === detalle.id) setDetalle(await apiFetch<TerceroDetalle>(`/terceros/${editId}`));
    } catch (err) {
      setErrorForm(err instanceof ApiError ? err.message : "No se pudo guardar");
    } finally {
      setGuardando(false);
    }
  }

  async function abrirDetalle(t: Tercero) {
    const [d, pg] = await Promise.all([
      apiFetch<TerceroDetalle>(`/terceros/${t.id}`),
      apiFetch<CfdiPage>(`/cfdi?limit=50&${esCliente ? "receptor" : "emisor"}=${encodeURIComponent(t.rfc)}`),
    ]);
    setDetalle(d);
    setCfdis(pg.items.filter((c) => (esCliente ? c.rfc_receptor === t.rfc : c.rfc_emisor === t.rfc)));
  }

  if (!empresaActiva) return null;
  const totalSaldo = items.reduce((a, t) => a + t.saldo_pendiente, 0);
  const total12m = items.reduce((a, t) => a + t.facturado_12m, 0);
  const conSaldo = items.filter((t) => t.saldo_pendiente > 0).length;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">{titulo}</h1>
          <p className="text-sm text-muted-foreground">
            {esCliente ? "A quién le facturas: se detectan solos de los CFDI emitidos." : "A quién le compras: se detectan solos de los CFDI recibidos."} Complementa contacto y condiciones de crédito.
          </p>
        </div>
        {puedeGestionar && (
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" onClick={sincronizar} disabled={sincronizando}><RefreshCw className={`mr-2 h-4 w-4 ${sincronizando ? "animate-spin" : ""}`} /> Detectar desde CFDI</Button>
            <Button variant="outline" onClick={() => setOpenCarga(true)}><FileUp className="mr-2 h-4 w-4" /> Importar Excel</Button>
            <Button onClick={abrirNuevo}><Plus className="mr-2 h-4 w-4" /> Nuevo {esCliente ? "cliente" : "proveedor"}</Button>
            <CargaMasivaDialog open={openCarga} onOpenChange={setOpenCarga} titulo={`Importar ${titulo.toLowerCase()} desde Excel`} descripcion="Columnas: RFC, Nombre, Tipo (cliente/proveedor/ambos), Email, Teléfono, Contacto, Días crédito, Límite crédito, Código postal, Régimen, Notas. El RFC existente se actualiza." endpointImportar="/terceros/importar" endpointPlantilla="/terceros/plantilla" nombrePlantilla="plantilla_terceros.xlsx" etiquetaCreados="nuevos" etiquetaActualizados="actualizados" onImportado={() => void cargar()} />
          </div>
        )}
      </div>

      {msg && <p className="rounded-md border p-2 text-sm text-muted-foreground">{msg}</p>}

      <div className="grid gap-3 sm:grid-cols-3">
        <StatTile label={`${titulo} activos`} value={String(items.length)} hint={`${conSaldo} con saldo pendiente`} />
        <StatTile label={esCliente ? "Facturado últimos 12 meses" : "Comprado últimos 12 meses"} value={formatMoney(total12m)} />
        <StatTile label={esCliente ? "Por cobrar (PPD sin REP)" : "Por pagar (PPD sin REP)"} value={formatMoney(totalSaldo)} tone={totalSaldo > 0 ? "critical" : "default"} />
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <div className="relative w-80">
          <Search className="pointer-events-none absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input className="pl-8" placeholder="Buscar por RFC, nombre, contacto o correo…" value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
        <Select value={activo} onValueChange={setActivo}>
          <SelectTrigger className="w-[150px]"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="true">Activos</SelectItem>
            <SelectItem value="false">Inactivos</SelectItem>
            <SelectItem value={TODOS}>Todos</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <Card>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>RFC</TableHead>
                  <TableHead>Nombre</TableHead>
                  <TableHead>Contacto</TableHead>
                  <TableHead className="text-right">Crédito</TableHead>
                  <TableHead className="text-right">CFDIs</TableHead>
                  <TableHead className="text-right">Últimos 12 m</TableHead>
                  <TableHead className="text-right">{esCliente ? "Por cobrar" : "Por pagar"}</TableHead>
                  <TableHead>Último CFDI</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody className={loading ? "opacity-50" : ""}>
                {items.length === 0 && !loading && (
                  <TableRow><TableCell colSpan={8} className="py-8 text-center text-muted-foreground">Sin {titulo.toLowerCase()}. {puedeGestionar && 'Usa "Detectar desde CFDI" para llenar el catálogo con la bóveda.'}</TableCell></TableRow>
                )}
                {items.map((t) => (
                  <TableRow key={t.id} className="cursor-pointer" onClick={() => abrirDetalle(t)}>
                    <TableCell className="font-mono text-xs">{t.rfc}</TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <span className="max-w-72 truncate" title={t.nombre}>{t.nombre}</span>
                        {t.es_efos && <Badge variant="destructive" title="RFC en lista de EFOS (art. 69-B)"><AlertTriangle className="mr-1 h-3 w-3" />EFOS</Badge>}
                        {t.tipo === "ambos" && <Badge variant="outline">cliente y proveedor</Badge>}
                        {!t.activo && <Badge variant="secondary">inactivo</Badge>}
                      </div>
                    </TableCell>
                    <TableCell className="text-xs">{t.contacto ?? ""}{t.email ? <span className="block text-muted-foreground">{t.email}</span> : null}</TableCell>
                    <TableCell className="text-right text-xs tabular-nums">{t.dias_credito ? `${t.dias_credito} días` : "—"}{t.limite_credito != null ? <span className="block text-muted-foreground">{formatMoney(t.limite_credito)}</span> : null}</TableCell>
                    <TableCell className="text-right tabular-nums">{t.num_cfdis}</TableCell>
                    <TableCell className="text-right tabular-nums">{formatMoney(t.facturado_12m)}</TableCell>
                    <TableCell className={`text-right font-medium tabular-nums ${t.saldo_pendiente > 0 ? "text-[color:var(--status-critical)]" : "text-muted-foreground"}`}>{formatMoney(t.saldo_pendiente)}</TableCell>
                    <TableCell className="whitespace-nowrap text-xs">{t.ultimo_cfdi ? formatDate(t.ultimo_cfdi) : "—"}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>

      {/* Alta / edición */}
      <Dialog open={openForm} onOpenChange={setOpenForm}>
        <DialogContent className="max-w-xl">
          <DialogHeader>
            <DialogTitle>{editId ? "Editar" : "Nuevo"} {form.tipo === "ambos" ? "cliente / proveedor" : form.tipo}</DialogTitle>
            <DialogDescription>Los datos fiscales se toman de los CFDI; aquí se complementan contacto y condiciones comerciales.</DialogDescription>
          </DialogHeader>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5"><Label>RFC</Label><Input value={form.rfc} disabled={!!editId} onChange={(e) => setForm({ ...form, rfc: e.target.value.toUpperCase() })} maxLength={13} /></div>
            <div className="space-y-1.5">
              <Label>Tipo</Label>
              <Select value={form.tipo} onValueChange={(v) => setForm({ ...form, tipo: v as TerceroTipo })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent><SelectItem value="cliente">Cliente</SelectItem><SelectItem value="proveedor">Proveedor</SelectItem><SelectItem value="ambos">Ambos</SelectItem></SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5 sm:col-span-2"><Label>Nombre / razón social</Label><Input value={form.nombre} onChange={(e) => setForm({ ...form, nombre: e.target.value })} /></div>
            <div className="space-y-1.5"><Label>Contacto</Label><Input value={form.contacto} onChange={(e) => setForm({ ...form, contacto: e.target.value })} /></div>
            <div className="space-y-1.5"><Label>Correo</Label><Input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></div>
            <div className="space-y-1.5"><Label>Teléfono</Label><Input value={form.telefono} onChange={(e) => setForm({ ...form, telefono: e.target.value })} /></div>
            <div className="space-y-1.5"><Label>Código postal</Label><Input value={form.codigo_postal} maxLength={5} onChange={(e) => setForm({ ...form, codigo_postal: e.target.value })} /></div>
            <div className="space-y-1.5"><Label>Días de crédito</Label><Input type="number" min={0} value={form.dias_credito} onChange={(e) => setForm({ ...form, dias_credito: e.target.value })} /></div>
            <div className="space-y-1.5"><Label>Límite de crédito</Label><Input type="number" min={0} step="0.01" value={form.limite_credito} onChange={(e) => setForm({ ...form, limite_credito: e.target.value })} /></div>
            <div className="space-y-1.5"><Label>Régimen fiscal</Label><Input value={form.regimen_fiscal_codigo} maxLength={3} placeholder="601" onChange={(e) => setForm({ ...form, regimen_fiscal_codigo: e.target.value })} /></div>
            <div className="flex items-end gap-2 pb-2"><input id="activo" type="checkbox" className="h-4 w-4" checked={form.activo} onChange={(e) => setForm({ ...form, activo: e.target.checked })} /><Label htmlFor="activo">Activo</Label></div>
            <div className="space-y-1.5 sm:col-span-2"><Label>Notas</Label><Input value={form.notas} onChange={(e) => setForm({ ...form, notas: e.target.value })} /></div>
          </div>
          {errorForm && <p className="text-sm text-destructive">{errorForm}</p>}
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpenForm(false)}>Cancelar</Button>
            <Button onClick={guardar} disabled={guardando || !form.nombre.trim() || (!editId && form.rfc.trim().length < 12)}>{guardando ? "Guardando…" : "Guardar"}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Detalle */}
      <Dialog open={!!detalle} onOpenChange={(o) => !o && setDetalle(null)}>
        <DialogContent className="max-w-3xl">
          {detalle && (
            <>
              <DialogHeader>
                <DialogTitle className="flex flex-wrap items-center gap-2">
                  {detalle.nombre}
                  {detalle.es_efos && <Badge variant="destructive">EFOS</Badge>}
                  <Badge variant="outline">{detalle.tipo}</Badge>
                </DialogTitle>
                <DialogDescription className="font-mono">{detalle.rfc}{detalle.regimen_fiscal_codigo ? ` · régimen ${detalle.regimen_fiscal_codigo}` : ""}{detalle.codigo_postal ? ` · CP ${detalle.codigo_postal}` : ""}</DialogDescription>
              </DialogHeader>
              <Tabs defaultValue="saldos">
                <TabsList>
                  <TabsTrigger value="saldos">Saldos y antigüedad</TabsTrigger>
                  <TabsTrigger value="cfdis">CFDI ({cfdis.length})</TabsTrigger>
                  <TabsTrigger value="datos">Datos</TabsTrigger>
                </TabsList>
                <TabsContent value="saldos" className="space-y-3 pt-3">
                  <div className="grid gap-3 sm:grid-cols-3">
                    <StatTile label="Total facturado (emitido)" value={formatMoney(detalle.total_emitido)} />
                    <StatTile label="Total comprado (recibido)" value={formatMoney(detalle.total_recibido)} />
                    <StatTile label="Últimos 12 meses" value={formatMoney(detalle.facturado_12m)} hint={`${detalle.num_cfdis} CFDI en total`} />
                  </div>
                  <TablaAntiguedad titulo="Por cobrar (facturas PPD emitidas sin REP)" a={detalle.por_cobrar} />
                  <TablaAntiguedad titulo="Por pagar (facturas PPD recibidas sin REP)" a={detalle.por_pagar} />
                </TabsContent>
                <TabsContent value="cfdis" className="pt-3">
                  <div className="max-h-96 overflow-auto rounded-md border">
                    <Table>
                      <TableHeader><TableRow><TableHead>Fecha</TableHead><TableHead>Tipo</TableHead><TableHead>Serie/Folio</TableHead><TableHead>Método</TableHead><TableHead className="text-right">Total</TableHead><TableHead>Estatus</TableHead></TableRow></TableHeader>
                      <TableBody>
                        {cfdis.map((c) => (
                          <TableRow key={c.id}>
                            <TableCell className="whitespace-nowrap">{formatDate(c.fecha)}</TableCell>
                            <TableCell className="capitalize">{c.tipo.replace("_", " ")}</TableCell>
                            <TableCell className="font-mono text-xs">{[c.serie, c.folio].filter(Boolean).join("-") || "—"}</TableCell>
                            <TableCell>{c.metodo_pago_codigo ?? "—"}</TableCell>
                            <TableCell className="text-right tabular-nums">{formatMoney2(c.total)}</TableCell>
                            <TableCell><Badge variant={c.estatus === "vigente" ? "secondary" : "destructive"}>{c.estatus}</Badge></TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </div>
                  <p className="mt-2 text-xs text-muted-foreground">Ver todos con filtros en <Link href="/cfdi" className="underline">CFDI</Link>.</p>
                </TabsContent>
                <TabsContent value="datos" className="pt-3">
                  <dl className="grid gap-x-6 gap-y-2 text-sm sm:grid-cols-2">
                    <Fila k="Contacto" v={detalle.contacto ?? "—"} /><Fila k="Correo" v={detalle.email ?? "—"} /><Fila k="Teléfono" v={detalle.telefono ?? "—"} />
                    <Fila k="Días de crédito" v={String(detalle.dias_credito)} /><Fila k="Límite de crédito" v={detalle.limite_credito != null ? formatMoney(detalle.limite_credito) : "—"} />
                    <Fila k="Origen" v={detalle.origen === "cfdi" ? "Detectado en la bóveda" : detalle.origen === "excel" ? "Carga masiva" : "Captura manual"} />
                    <Fila k="Notas" v={detalle.notas ?? "—"} />
                  </dl>
                  {puedeGestionar && <Button className="mt-4" variant="outline" onClick={() => { const t = items.find((x) => x.id === detalle.id); if (t) abrirEditar(t); }}>Editar</Button>}
                </TabsContent>
              </Tabs>
            </>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}

function Fila({ k, v }: { k: string; v: string }) {
  return (<div className="flex justify-between gap-3"><dt className="text-muted-foreground">{k}</dt><dd className="text-right">{v}</dd></div>);
}

function TablaAntiguedad({ titulo, a }: { titulo: string; a: TerceroDetalle["por_cobrar"] }) {
  return (
    <div className="rounded-md border p-3">
      <div className="mb-2 flex items-center justify-between text-sm"><span className="font-medium">{titulo}</span><span className="tabular-nums">{formatMoney2(a.total)} · {a.num_cfdis} facturas</span></div>
      <div className="grid grid-cols-4 gap-2 text-center text-xs">
        {[["0–30 días", a.d0_30], ["31–60", a.d31_60], ["61–90", a.d61_90], ["> 90", a.d90_mas]].map(([k, v]) => (
          <div key={String(k)} className="rounded-md bg-muted/40 p-2"><p className="text-muted-foreground">{k}</p><p className={`font-semibold tabular-nums ${Number(v) > 0 && String(k) === "> 90" ? "text-[color:var(--status-critical)]" : ""}`}>{formatMoney2(Number(v))}</p></div>
        ))}
      </div>
    </div>
  );
}
