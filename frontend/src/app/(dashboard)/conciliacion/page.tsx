"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { CheckCircle2, FileUp, Link2, Plus, Search, Sparkles, Unlink, X, XCircle } from "lucide-react";

import { useEmpresa } from "@/components/empresa-provider";
import { MESES_LARGO, PeriodoSelector } from "@/components/impuestos/periodo-selector";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ApiError, apiFetch } from "@/lib/api";
import { formatDate, formatMoney2 } from "@/lib/format";
import { PERM, can } from "@/lib/permissions";
import { cn } from "@/lib/utils";
import type {
  AutoConciliarResponse,
  CandidatoCfdi,
  CandidatosResponse,
  CoincidenciaCfdi,
  CombinacionCfdi,
  CuentaBancaria,
  Declaracion,
  ImportarBancoResponse,
  MovimientoBanco,
  MovimientosBancoPage,
  ResumenConciliacion,
} from "@/lib/types";

const TODAS = "__todas__";
const ESTADO_VARIANT = { pendiente: "warning", parcial: "default", conciliado: "success", ignorado: "secondary" } as const;
const COINCIDENCIA: Record<CoincidenciaCfdi, { label: string; variant: "success" | "warning" | "outline" | "secondary"; hint: string }> = {
  exacto: { label: "Exacto", variant: "success", hint: "El saldo del CFDI es igual a lo que falta del movimiento" },
  similar: { label: "Similar", variant: "warning", hint: "Difiere unos pesos (comisión bancaria o redondeo)" },
  parcial: { label: "Parcial", variant: "outline", hint: "El CFDI es mayor: este movimiento lo paga en parte" },
  menor: { label: "Menor", variant: "secondary", hint: "El CFDI es menor: se puede combinar con otros del mismo cliente" },
};
const VENTANAS = [
  { dias: 30, label: "±1 mes" },
  { dias: 120, label: "4 meses atrás" },
  { dias: 365, label: "1 año atrás" },
];
const TOL = 0.011;

export default function ConciliacionPage() {
  const { empresaActiva } = useEmpresa();
  const hoy = new Date();
  const [anio, setAnio] = useState(hoy.getFullYear());
  const [mes, setMes] = useState(hoy.getMonth() + 1);
  const [tab, setTab] = useState("resumen");

  // resumen + declaración
  const [resumen, setResumen] = useState<ResumenConciliacion | null>(null);
  const [openDecl, setOpenDecl] = useState(false);
  const [decl, setDecl] = useState<Partial<Declaracion>>({});
  const [guardandoDecl, setGuardandoDecl] = useState(false);
  const [errorDecl, setErrorDecl] = useState<string | null>(null);

  // bancos
  const [cuentas, setCuentas] = useState<CuentaBancaria[]>([]);
  const [cuentaId, setCuentaId] = useState(TODAS);
  const [estado, setEstado] = useState(TODAS);
  const [movs, setMovs] = useState<MovimientosBancoPage | null>(null);
  const [loadingMovs, setLoadingMovs] = useState(false);
  const [openCuenta, setOpenCuenta] = useState(false);
  const [nuevaCuenta, setNuevaCuenta] = useState({ banco: "", alias: "", numero: "" });
  const [errorCuenta, setErrorCuenta] = useState<string | null>(null);
  const [openImport, setOpenImport] = useState(false);
  const [archivo, setArchivo] = useState<File | null>(null);
  const [cuentaImport, setCuentaImport] = useState("");
  const [importando, setImportando] = useState(false);
  const [resImport, setResImport] = useState<ImportarBancoResponse | null>(null);
  const [errorImport, setErrorImport] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const [autoRes, setAutoRes] = useState<AutoConciliarResponse | null>(null);
  const [autoLoading, setAutoLoading] = useState(false);

  // diálogo de movimiento (conciliación asistida)
  const [movSel, setMovSel] = useState<MovimientoBanco | null>(null);
  const [cand, setCand] = useState<CandidatosResponse | null>(null);
  const [buscando, setBuscando] = useState(false);
  const [qCand, setQCand] = useState("");
  const [ventana, setVentana] = useState(120);
  const [sel, setSel] = useState<Record<string, number>>({}); // cfdi_id → importe a ligar
  const [notaIgnorar, setNotaIgnorar] = useState("");
  const [accionLoading, setAccionLoading] = useState(false);
  const [errorAccion, setErrorAccion] = useState<string | null>(null);

  const puedeGestionar = !!empresaActiva && can(empresaActiva.permisos, PERM.CONCILIACION_GESTIONAR);

  const cargarResumen = useCallback(async () => {
    setResumen(await apiFetch<ResumenConciliacion>(`/conciliacion/resumen?anio=${anio}&mes=${mes}`));
  }, [anio, mes]);

  const cargarMovs = useCallback(async () => {
    setLoadingMovs(true);
    try {
      const p = new URLSearchParams({ anio: String(anio), mes: String(mes), limit: "500" });
      if (cuentaId !== TODAS) p.set("cuenta_id", cuentaId);
      if (estado !== TODAS) p.set("estado", estado);
      setMovs(await apiFetch<MovimientosBancoPage>(`/conciliacion/bancos/movimientos?${p}`));
    } finally {
      setLoadingMovs(false);
    }
  }, [anio, mes, cuentaId, estado]);

  const cargarCuentas = useCallback(async () => {
    const c = await apiFetch<CuentaBancaria[]>("/conciliacion/cuentas");
    setCuentas(c);
    if (c.length && !cuentaImport) setCuentaImport(c[0].id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!empresaActiva) return;
    void cargarCuentas();
  }, [empresaActiva, cargarCuentas]);
  useEffect(() => {
    if (!empresaActiva) return;
    void cargarResumen();
    void cargarMovs();
  }, [empresaActiva, cargarResumen, cargarMovs]);

  // ----- acciones -----
  async function guardarDecl() {
    setGuardandoDecl(true);
    setErrorDecl(null);
    try {
      const num = (v: unknown) => (v === "" || v == null ? null : Number(v));
      await apiFetch(`/conciliacion/declaraciones/${anio}/${mes}`, {
        method: "PUT",
        body: JSON.stringify({
          ingresos_declarados: num(decl.ingresos_declarados),
          deducciones_declaradas: num(decl.deducciones_declaradas),
          iva_declarado: num(decl.iva_declarado),
          isr_declarado: num(decl.isr_declarado),
          fecha_presentacion: decl.fecha_presentacion || null,
          numero_operacion: decl.numero_operacion || null,
          notas: decl.notas || null,
        }),
      });
      setOpenDecl(false);
      await cargarResumen();
    } catch (err) {
      setErrorDecl(err instanceof ApiError ? err.message : "No se pudo guardar");
    } finally {
      setGuardandoDecl(false);
    }
  }

  async function crearCuenta() {
    setErrorCuenta(null);
    try {
      await apiFetch("/conciliacion/cuentas", {
        method: "POST",
        body: JSON.stringify({ banco: nuevaCuenta.banco, alias: nuevaCuenta.alias, numero: nuevaCuenta.numero || null }),
      });
      setOpenCuenta(false);
      setNuevaCuenta({ banco: "", alias: "", numero: "" });
      await cargarCuentas();
    } catch (err) {
      setErrorCuenta(err instanceof ApiError ? err.message : "No se pudo crear la cuenta");
    }
  }

  async function importar() {
    if (!archivo || !cuentaImport) {
      setErrorImport("Selecciona la cuenta y el archivo");
      return;
    }
    setImportando(true);
    setErrorImport(null);
    try {
      const form = new FormData();
      form.append("archivo", archivo);
      form.append("cuenta_id", cuentaImport);
      setResImport(await apiFetch<ImportarBancoResponse>("/conciliacion/bancos/importar", { method: "POST", body: form }));
      await Promise.all([cargarMovs(), cargarResumen()]);
    } catch (err) {
      setErrorImport(err instanceof ApiError ? err.message : "Error al importar");
    } finally {
      setImportando(false);
    }
  }

  async function autoConciliar() {
    setAutoLoading(true);
    try {
      setAutoRes(
        await apiFetch<AutoConciliarResponse>("/conciliacion/bancos/auto", {
          method: "POST",
          body: JSON.stringify({ anio, mes, cuenta_id: cuentaId === TODAS ? null : cuentaId, tolerancia_dias: 5 }),
        }),
      );
      await Promise.all([cargarMovs(), cargarResumen()]);
    } finally {
      setAutoLoading(false);
    }
  }

  // ----- diálogo de conciliación asistida -----
  const cargarCandidatos = useCallback(async (m: MovimientoBanco, opts: { q?: string; dias?: number }) => {
    setBuscando(true);
    try {
      const p = new URLSearchParams({ dias_atras: String(opts.dias ?? 120) });
      if (opts.q?.trim()) p.set("q", opts.q.trim());
      setCand(await apiFetch<CandidatosResponse>(`/conciliacion/bancos/movimientos/${m.id}/candidatos?${p}`));
    } catch (err) {
      setErrorAccion(err instanceof ApiError ? err.message : "No se pudieron buscar candidatos");
    } finally {
      setBuscando(false);
    }
  }, []);

  async function abrirMov(m: MovimientoBanco) {
    setMovSel(m);
    setCand(null);
    setSel({});
    setQCand("");
    setVentana(120);
    setErrorAccion(null);
    setNotaIgnorar(m.nota ?? "");
    if (m.estado !== "ignorado" && m.restante > TOL) await cargarCandidatos(m, { dias: 120 });
  }

  /** Ejecuta una acción sobre el movimiento abierto. Con `mantener` el diálogo
   *  sigue abierto con el movimiento actualizado (p. ej. al quitar una liga). */
  async function accion(path: string, opts: { method?: string; body?: unknown; mantener?: boolean } = {}) {
    if (!movSel) return;
    setAccionLoading(true);
    setErrorAccion(null);
    try {
      const actualizado = await apiFetch<MovimientoBanco>(`/conciliacion/bancos/movimientos/${movSel.id}/${path}`, {
        method: opts.method ?? "POST",
        ...(opts.method === "DELETE" ? {} : { body: JSON.stringify(opts.body ?? {}) }),
      });
      if (opts.mantener) {
        setMovSel(actualizado);
        setSel({});
        if (actualizado.estado !== "ignorado" && actualizado.restante > TOL) await cargarCandidatos(actualizado, { q: qCand, dias: ventana });
        else setCand(null);
      } else {
        setMovSel(null);
      }
      await Promise.all([cargarMovs(), cargarResumen()]);
    } catch (err) {
      setErrorAccion(err instanceof ApiError ? err.message : "No se pudo aplicar");
    } finally {
      setAccionLoading(false);
    }
  }

  const restante = cand?.movimiento.restante ?? movSel?.restante ?? 0;
  const sumaSel = useMemo(() => Object.values(sel).reduce((a, b) => a + (Number.isFinite(b) ? b : 0), 0), [sel]);
  const restanteTrasSel = Math.round((restante - sumaSel) * 100) / 100;

  function toggleSel(c: CandidatoCfdi) {
    setSel((prev) => {
      if (prev[c.cfdi_id] != null) {
        const { [c.cfdi_id]: _omit, ...resto } = prev; // eslint-disable-line @typescript-eslint/no-unused-vars
        return resto;
      }
      const disponible = Math.max(0, restante - Object.values(prev).reduce((a, b) => a + b, 0));
      return { ...prev, [c.cfdi_id]: Math.round(Math.min(c.saldo, disponible) * 100) / 100 };
    });
  }

  function aplicarCombo(combo: CombinacionCfdi) {
    if (!cand) return;
    const porId = new Map(cand.candidatos.map((c) => [c.cfdi_id, c]));
    const nuevo: Record<string, number> = {};
    for (const id of combo.cfdi_ids) nuevo[id] = porId.get(id)?.saldo ?? 0;
    setSel(nuevo);
  }

  function ligarSeleccion(ids?: string[]) {
    const ligas = (ids ?? Object.keys(sel)).map((cfdi_id) => ({ cfdi_id, importe: ids ? undefined : sel[cfdi_id] }));
    if (ligas.length === 0) return;
    void accion("conciliar", { body: { ligas }, mantener: restanteTrasSel > TOL && !ids });
  }

  if (!empresaActiva) return null;
  const periodoTxt = `${MESES_LARGO[mes - 1]} ${anio}`;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Conciliación</h1>
          <p className="text-sm text-muted-foreground">
            Compara lo que hay en el SAT (bóveda de CFDI), lo que pasó por el banco y lo que se declaró — {periodoTxt}.
          </p>
        </div>
        <PeriodoSelector
          anio={anio}
          mes={mes}
          anios={[hoy.getFullYear(), hoy.getFullYear() - 1]}
          permitirAnual={false}
          onChange={(a, m) => {
            setAnio(a);
            setMes(m ?? 1);
          }}
        />
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="resumen">Resumen SAT · Banco · Declarado</TabsTrigger>
          <TabsTrigger value="bancos">Bancos {movs ? `(${movs.total})` : ""}</TabsTrigger>
        </TabsList>

        {/* ---------------- RESUMEN ---------------- */}
        <TabsContent value="resumen" className="mt-4 space-y-4">
          {resumen && (
            <>
              <div
                className={cn(
                  "rounded-md border p-3 text-sm",
                  resumen.semaforo === "ok" && "border-emerald-500/40 bg-emerald-500/10",
                  resumen.semaforo === "revisar" && "border-red-500/40 bg-red-500/10",
                  resumen.semaforo === "sin_declaracion" && "border-amber-500/40 bg-amber-500/10",
                )}
              >
                {resumen.semaforo === "ok" && "Lo calculado con la bóveda coincide con lo declarado (diferencias < $1)."}
                {resumen.semaforo === "revisar" && "Hay diferencias entre lo calculado con la bóveda y lo declarado. Revisa antes del cierre."}
                {resumen.semaforo === "sin_declaracion" && "Aún no se captura lo declarado de este periodo. "}
                {puedeGestionar && (
                  <Button
                    size="sm"
                    variant="outline"
                    className="ml-2"
                    onClick={() => {
                      setDecl(resumen.declarado);
                      setErrorDecl(null);
                      setOpenDecl(true);
                    }}
                  >
                    {resumen.declarado.capturada ? "Editar declaración" : "Capturar declaración"}
                  </Button>
                )}
              </div>

              <div className="grid gap-4 lg:grid-cols-3">
                <Columna titulo="SAT · bóveda de CFDI" sub={`${resumen.sat.num_cfdis} comprobantes del mes`}>
                  <Fila k="Ingresos cobrados (base)" v={formatMoney2(resumen.sat.ingresos_cobrados)} />
                  <Fila k="Ingresos facturados (incl. PPD)" v={formatMoney2(resumen.sat.ingresos_facturados)} muted />
                  <Fila k="Gastos pagados (base)" v={formatMoney2(resumen.sat.egresos_pagados)} />
                  <Fila k={resumen.sat.iva_saldo >= 0 ? "IVA a cargo" : "IVA a favor"} v={formatMoney2(Math.abs(resumen.sat.iva_saldo))} strong />
                  <Fila k="ISR pago provisional" v={formatMoney2(resumen.sat.isr_estimado)} strong />
                </Columna>
                <Columna
                  titulo="Banco · estados de cuenta"
                  sub={`${resumen.banco.num_movimientos} movimientos · ${resumen.banco.porcentaje_conciliado}% conciliado`}
                >
                  <Fila k="Abonos (entradas)" v={formatMoney2(resumen.banco.abonos)} />
                  <Fila k="Abonos ligados a CFDI" v={formatMoney2(resumen.banco.abonos_conciliados)} muted />
                  <Fila k="Cargos (salidas)" v={formatMoney2(resumen.banco.cargos)} />
                  <Fila k="Cargos ligados a CFDI" v={formatMoney2(resumen.banco.cargos_conciliados)} muted />
                  <Fila k="Pendientes / parciales / ignorados" v={`${resumen.banco.pendientes} / ${resumen.banco.parciales} / ${resumen.banco.ignorados}`} />
                </Columna>
                <Columna
                  titulo="Declarado al SAT"
                  sub={
                    resumen.declarado.capturada
                      ? `Presentada ${resumen.declarado.fecha_presentacion ? formatDate(resumen.declarado.fecha_presentacion) : ""} ${resumen.declarado.numero_operacion ? `· op. ${resumen.declarado.numero_operacion}` : ""}`
                      : "Sin capturar"
                  }
                >
                  <Fila k="Ingresos declarados" v={fmtN(resumen.declarado.ingresos_declarados)} />
                  <Fila k="Deducciones declaradas" v={fmtN(resumen.declarado.deducciones_declaradas)} muted />
                  <Fila k="IVA declarado" v={fmtN(resumen.declarado.iva_declarado)} strong />
                  <Fila k="ISR declarado" v={fmtN(resumen.declarado.isr_declarado)} strong />
                  {resumen.declarado.notas && <p className="pt-2 text-xs text-muted-foreground">{resumen.declarado.notas}</p>}
                </Columna>
              </div>

              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-base">Diferencias</CardTitle>
                </CardHeader>
                <CardContent className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                  <Dif
                    k="Ingresos SAT (con IVA) − abonos banco"
                    v={resumen.diferencias.ingresos_sat_vs_banco}
                    hint="Positivo: cobros facturados que no aparecen en el banco (o PPD sin REP)"
                  />
                  <Dif k="Ingresos SAT − declarados" v={resumen.diferencias.ingresos_sat_vs_declarado} />
                  <Dif k="IVA SAT − declarado" v={resumen.diferencias.iva_sat_vs_declarado} />
                  <Dif k="ISR SAT − declarado" v={resumen.diferencias.isr_sat_vs_declarado} />
                </CardContent>
              </Card>
            </>
          )}
        </TabsContent>

        {/* ---------------- BANCOS ---------------- */}
        <TabsContent value="bancos" className="mt-4 space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <Select value={cuentaId} onValueChange={setCuentaId}>
              <SelectTrigger className="w-[220px]">
                <SelectValue placeholder="Cuenta" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={TODAS}>Todas las cuentas</SelectItem>
                {cuentas.map((c) => (
                  <SelectItem key={c.id} value={c.id}>
                    {c.alias} · {c.banco}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select value={estado} onValueChange={setEstado}>
              <SelectTrigger className="w-[170px]">
                <SelectValue placeholder="Estado" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={TODAS}>Todos los estados</SelectItem>
                <SelectItem value="pendiente">Pendientes</SelectItem>
                <SelectItem value="parcial">Parciales</SelectItem>
                <SelectItem value="conciliado">Conciliados</SelectItem>
                <SelectItem value="ignorado">Ignorados</SelectItem>
              </SelectContent>
            </Select>
            <div className="ml-auto flex flex-wrap gap-2">
              {puedeGestionar && (
                <>
                  <Button
                    variant="outline"
                    onClick={() => {
                      setNuevaCuenta({ banco: "", alias: "", numero: "" });
                      setErrorCuenta(null);
                      setOpenCuenta(true);
                    }}
                  >
                    <Plus className="mr-2 h-4 w-4" /> Cuenta
                  </Button>
                  <Button
                    variant="outline"
                    onClick={() => {
                      setArchivo(null);
                      setResImport(null);
                      setErrorImport(null);
                      if (inputRef.current) inputRef.current.value = "";
                      setOpenImport(true);
                    }}
                    disabled={cuentas.length === 0}
                  >
                    <FileUp className="mr-2 h-4 w-4" /> Importar estado de cuenta
                  </Button>
                  <Button onClick={autoConciliar} disabled={autoLoading || !movs?.total}>
                    <Sparkles className="mr-2 h-4 w-4" /> {autoLoading ? "Conciliando…" : "Conciliar automáticamente"}
                  </Button>
                </>
              )}
            </div>
          </div>
          {autoRes && (
            <p className="rounded-md border p-2 text-sm text-muted-foreground">
              Auto: {autoRes.conciliados} de {autoRes.revisados} pendientes ligados a un CFDI de monto exacto · {autoRes.ambiguos} con varios CFDI del mismo
              monto (elige a mano) · {autoRes.con_sugerencias} con sugerencias (similares, parciales o varias facturas) · {autoRes.sin_coincidencia} sin
              coincidencia.
            </p>
          )}

          <Card>
            <CardContent className="p-0">
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Fecha</TableHead>
                      <TableHead>Cuenta</TableHead>
                      <TableHead>Concepto</TableHead>
                      <TableHead>Referencia</TableHead>
                      <TableHead className="text-right">Cargo</TableHead>
                      <TableHead className="text-right">Abono</TableHead>
                      <TableHead className="text-right">Saldo</TableHead>
                      <TableHead>Estado</TableHead>
                      <TableHead>CFDI</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody className={loadingMovs ? "opacity-50" : ""}>
                    {movs?.items.length === 0 && (
                      <TableRow>
                        <TableCell colSpan={9} className="py-8 text-center text-muted-foreground">
                          {cuentas.length === 0
                            ? "Registra una cuenta bancaria e importa su estado de cuenta (Excel o CSV)."
                            : "Sin movimientos en el periodo con esos filtros."}
                        </TableCell>
                      </TableRow>
                    )}
                    {movs?.items.map((m) => (
                      <TableRow key={m.id} className={puedeGestionar ? "cursor-pointer" : ""} onClick={puedeGestionar ? () => abrirMov(m) : undefined}>
                        <TableCell className="whitespace-nowrap">{formatDate(m.fecha)}</TableCell>
                        <TableCell className="text-xs">{m.cuenta_alias}</TableCell>
                        <TableCell className="max-w-72 truncate" title={m.concepto}>
                          {m.concepto}
                        </TableCell>
                        <TableCell className="font-mono text-xs">{m.referencia ?? "—"}</TableCell>
                        <TableCell className="text-right tabular-nums text-[color:var(--status-critical)]">{m.cargo ? formatMoney2(m.cargo) : ""}</TableCell>
                        <TableCell className="text-right tabular-nums text-[color:var(--status-good)]">{m.abono ? formatMoney2(m.abono) : ""}</TableCell>
                        <TableCell className="text-right tabular-nums text-muted-foreground">{m.saldo != null ? formatMoney2(m.saldo) : ""}</TableCell>
                        <TableCell>
                          <Badge variant={ESTADO_VARIANT[m.estado]}>
                            {m.estado}
                            {m.conciliado_por === "auto" ? " · auto" : ""}
                          </Badge>
                        </TableCell>
                        <TableCell className="max-w-56 text-xs" title={m.cfdi_uuid ?? ""}>
                          {m.cfdi_nombre ? (
                            <>
                              <span className="block truncate">{m.cfdi_nombre}</span>
                              {m.estado === "parcial" && (
                                <span className="text-muted-foreground">
                                  ligado {formatMoney2(m.importe_ligado)} · faltan {formatMoney2(m.restante)}
                                </span>
                              )}
                            </>
                          ) : m.nota ? (
                            <span className="text-muted-foreground">{m.nota}</span>
                          ) : (
                            "—"
                          )}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* Declaración */}
      <Dialog open={openDecl} onOpenChange={setOpenDecl}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Declaración {periodoTxt}</DialogTitle>
            <DialogDescription>Captura lo que se presentó al SAT para compararlo con lo calculado.</DialogDescription>
          </DialogHeader>
          <div className="grid gap-3 sm:grid-cols-2">
            <Campo
              label="Ingresos declarados"
              value={decl.ingresos_declarados}
              onChange={(v) => setDecl({ ...decl, ingresos_declarados: v as number | null })}
            />
            <Campo
              label="Deducciones declaradas"
              value={decl.deducciones_declaradas}
              onChange={(v) => setDecl({ ...decl, deducciones_declaradas: v as number | null })}
            />
            <Campo
              label="IVA declarado (a cargo +, a favor −)"
              value={decl.iva_declarado}
              onChange={(v) => setDecl({ ...decl, iva_declarado: v as number | null })}
            />
            <Campo label="ISR declarado" value={decl.isr_declarado} onChange={(v) => setDecl({ ...decl, isr_declarado: v as number | null })} />
            <div className="space-y-1.5">
              <Label>Fecha de presentación</Label>
              <Input type="date" value={decl.fecha_presentacion ?? ""} onChange={(e) => setDecl({ ...decl, fecha_presentacion: e.target.value })} />
            </div>
            <div className="space-y-1.5">
              <Label>Número de operación</Label>
              <Input value={decl.numero_operacion ?? ""} onChange={(e) => setDecl({ ...decl, numero_operacion: e.target.value })} />
            </div>
            <div className="space-y-1.5 sm:col-span-2">
              <Label>Notas</Label>
              <Input value={decl.notas ?? ""} onChange={(e) => setDecl({ ...decl, notas: e.target.value })} />
            </div>
          </div>
          {errorDecl && <p className="text-sm text-destructive">{errorDecl}</p>}
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpenDecl(false)}>
              Cancelar
            </Button>
            <Button onClick={guardarDecl} disabled={guardandoDecl}>
              {guardandoDecl ? "Guardando…" : "Guardar"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Nueva cuenta */}
      <Dialog open={openCuenta} onOpenChange={setOpenCuenta}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Nueva cuenta bancaria</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <div className="space-y-1.5">
              <Label>Banco</Label>
              <Input
                placeholder="BBVA, Banorte, Santander…"
                value={nuevaCuenta.banco}
                onChange={(e) => setNuevaCuenta({ ...nuevaCuenta, banco: e.target.value })}
              />
            </div>
            <div className="space-y-1.5">
              <Label>Alias</Label>
              <Input placeholder="Cuenta principal" value={nuevaCuenta.alias} onChange={(e) => setNuevaCuenta({ ...nuevaCuenta, alias: e.target.value })} />
            </div>
            <div className="space-y-1.5">
              <Label>Número / CLABE (opcional)</Label>
              <Input value={nuevaCuenta.numero} onChange={(e) => setNuevaCuenta({ ...nuevaCuenta, numero: e.target.value })} />
            </div>
            {errorCuenta && <p className="text-sm text-destructive">{errorCuenta}</p>}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpenCuenta(false)}>
              Cancelar
            </Button>
            <Button onClick={crearCuenta} disabled={!nuevaCuenta.banco || !nuevaCuenta.alias}>
              Crear
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Importar */}
      <Dialog open={openImport} onOpenChange={setOpenImport}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Importar estado de cuenta</DialogTitle>
            <DialogDescription>
              Excel (.xlsx) o CSV. Se detectan solas las columnas: fecha, concepto/descripción, referencia, cargo/retiro y abono/depósito (o una columna de
              importe con signo), saldo. Las filas ya importadas no se duplican.
            </DialogDescription>
          </DialogHeader>
          {resImport ? (
            <div className="space-y-2 text-sm">
              <p>
                <strong>{resImport.importados}</strong> movimientos importados{resImport.duplicados ? `, ${resImport.duplicados} duplicados omitidos` : ""}
                {resImport.fecha_min ? ` · del ${formatDate(resImport.fecha_min)} al ${formatDate(resImport.fecha_max!)}` : ""}.
              </p>
              <p className="text-xs text-muted-foreground">Columnas detectadas: {Object.keys(resImport.columnas_detectadas).join(", ")}</p>
              {resImport.advertencias.map((a) => (
                <p key={a} className="rounded-md border border-amber-500/40 bg-amber-500/10 p-2 text-xs">
                  {a}
                </p>
              ))}
              <DialogFooter>
                <Button onClick={() => setOpenImport(false)}>Cerrar</Button>
              </DialogFooter>
            </div>
          ) : (
            <div className="space-y-3">
              <div className="space-y-1.5">
                <Label>Cuenta</Label>
                <Select value={cuentaImport} onValueChange={setCuentaImport}>
                  <SelectTrigger>
                    <SelectValue placeholder="Cuenta" />
                  </SelectTrigger>
                  <SelectContent>
                    {cuentas.map((c) => (
                      <SelectItem key={c.id} value={c.id}>
                        {c.alias} · {c.banco}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label>Archivo</Label>
                <Input ref={inputRef} type="file" accept=".xlsx,.xlsm,.csv,.txt" onChange={(e) => setArchivo(e.target.files?.[0] ?? null)} />
              </div>
              {errorImport && <p className="text-sm text-destructive">{errorImport}</p>}
              <DialogFooter>
                <Button variant="outline" onClick={() => setOpenImport(false)}>
                  Cancelar
                </Button>
                <Button onClick={importar} disabled={importando}>
                  {importando ? "Importando…" : "Importar"}
                </Button>
              </DialogFooter>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Movimiento: conciliación asistida / ignorar */}
      <Dialog open={!!movSel} onOpenChange={(o) => !o && setMovSel(null)}>
        <DialogContent className="max-h-[90vh] w-[calc(100vw-2rem)] max-w-4xl overflow-y-auto overflow-x-hidden">
          {movSel && (
            <>
              <DialogHeader>
                <DialogTitle className="flex flex-wrap items-center gap-2">
                  {formatDate(movSel.fecha)} · {movSel.abono ? `Abono ${formatMoney2(movSel.abono)}` : `Cargo ${formatMoney2(movSel.cargo)}`}
                  <Badge variant={ESTADO_VARIANT[movSel.estado]}>
                    {movSel.estado}
                    {movSel.conciliado_por === "auto" ? " · auto" : ""}
                  </Badge>
                </DialogTitle>
                <DialogDescription>
                  {movSel.concepto}
                  {movSel.referencia ? ` · ref. ${movSel.referencia}` : ""} · {movSel.cuenta_alias}
                </DialogDescription>
              </DialogHeader>
              {/* min-w-0: sin esto la tabla ancha estira la columna del grid del diálogo y se sale del panel */}
              <div className="min-w-0 space-y-4">
                {/* Ligas actuales */}
                {movSel.ligas.length > 0 && (
                  <div className="rounded-md border">
                    <div className="flex flex-wrap items-center justify-between gap-2 border-b px-3 py-2 text-sm">
                      <p className="font-medium">
                        {movSel.ligas.length === 1 ? "Ligado a 1 CFDI" : `Ligado a ${movSel.ligas.length} CFDI`} · {formatMoney2(movSel.importe_ligado)}
                        {movSel.restante > TOL && <span className="ml-2 font-normal text-muted-foreground">faltan {formatMoney2(movSel.restante)}</span>}
                      </p>
                      <Button size="sm" variant="outline" onClick={() => accion("desconciliar")} disabled={accionLoading}>
                        <Unlink className="mr-2 h-4 w-4" /> Desconciliar todo
                      </Button>
                    </div>
                    <Table>
                      <TableBody>
                        {movSel.ligas.map((l) => (
                          <TableRow key={l.cfdi_id}>
                            <TableCell className="whitespace-nowrap text-xs">{formatDate(l.fecha)}</TableCell>
                            <TableCell>
                              <span className="block max-w-64 truncate text-sm">{l.nombre_contraparte}</span>
                              <span className="font-mono text-xs text-muted-foreground" title={l.uuid_fiscal}>
                                {l.serie_folio ?? l.uuid_fiscal.slice(0, 8)} · {l.tipo}
                              </span>
                            </TableCell>
                            <TableCell className="text-right tabular-nums">
                              {formatMoney2(l.importe)}
                              {Math.abs(l.importe - l.total) > TOL && <span className="block text-xs text-muted-foreground">de {formatMoney2(l.total)}</span>}
                            </TableCell>
                            <TableCell className="w-10 text-right">
                              <Button
                                size="icon"
                                variant="ghost"
                                className="h-7 w-7"
                                title="Quitar esta liga"
                                onClick={() => accion(`ligas/${l.cfdi_id}`, { method: "DELETE", mantener: true })}
                                disabled={accionLoading}
                              >
                                <X className="h-4 w-4" />
                              </Button>
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </div>
                )}

                {/* Búsqueda asistida */}
                {movSel.estado !== "ignorado" && movSel.restante > TOL && (
                  <div className="space-y-3">
                    <div className="flex flex-wrap items-end gap-2">
                      <div className="min-w-56 flex-1 space-y-1.5">
                        <Label>Buscar CFDI</Label>
                        <Input
                          placeholder="Cliente, RFC, folio o UUID (ignora el monto)"
                          value={qCand}
                          onChange={(e) => setQCand(e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === "Enter") void cargarCandidatos(movSel, { q: qCand, dias: ventana });
                          }}
                        />
                      </div>
                      <div className="space-y-1.5">
                        <Label>Ventana</Label>
                        <Select
                          value={String(ventana)}
                          onValueChange={(v) => {
                            setVentana(Number(v));
                            void cargarCandidatos(movSel, { q: qCand, dias: Number(v) });
                          }}
                        >
                          <SelectTrigger className="w-[150px]">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            {VENTANAS.map((v) => (
                              <SelectItem key={v.dias} value={String(v.dias)}>
                                {v.label}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                      <Button variant="outline" onClick={() => cargarCandidatos(movSel, { q: qCand, dias: ventana })} disabled={buscando}>
                        <Search className="mr-2 h-4 w-4" /> Buscar
                      </Button>
                    </div>

                    {cand && cand.combinaciones.length > 0 && (
                      <div className="rounded-md border border-emerald-500/40 bg-emerald-500/10 p-2 text-sm">
                        <p className="mb-1 font-medium">Varias facturas que juntas suman lo que falta</p>
                        <div className="flex flex-wrap gap-2">
                          {cand.combinaciones.map((co, i) => (
                            <Button key={i} size="sm" variant="outline" onClick={() => aplicarCombo(co)}>
                              {co.cfdi_ids.length} CFDI · <span className="mx-1 max-w-40 truncate">{co.nombre_contraparte}</span> · {formatMoney2(co.total)}
                              {Math.abs(co.diferencia) > TOL ? ` (${co.diferencia > 0 ? "+" : ""}${formatMoney2(co.diferencia)})` : ""}
                            </Button>
                          ))}
                        </div>
                      </div>
                    )}

                    {buscando || cand === null ? (
                      <p className="text-sm text-muted-foreground">Buscando…</p>
                    ) : cand.candidatos.length === 0 ? (
                      <p className="text-sm text-muted-foreground">
                        Ningún CFDI vigente con saldo coincide. Amplía la ventana, busca por cliente o folio, o si es comisión, traspaso, intereses o un
                        depósito sin factura, márcalo como ignorado.
                      </p>
                    ) : (
                      <div className="overflow-x-auto rounded-md border">
                        <Table>
                          <TableHeader>
                            <TableRow>
                              <TableHead className="w-8"></TableHead>
                              <TableHead>Coincidencia</TableHead>
                              <TableHead>Fecha</TableHead>
                              <TableHead>Contraparte</TableHead>
                              <TableHead>CFDI</TableHead>
                              <TableHead className="text-right">Saldo</TableHead>
                              <TableHead className="text-right">Importe a ligar</TableHead>
                              <TableHead></TableHead>
                            </TableRow>
                          </TableHeader>
                          <TableBody>
                            {cand.candidatos.map((c) => {
                              const marcado = sel[c.cfdi_id] != null;
                              const info = COINCIDENCIA[c.coincidencia];
                              return (
                                <TableRow key={c.cfdi_id} className={cn("cursor-pointer", marcado && "bg-muted/50")} onClick={() => toggleSel(c)}>
                                  <TableCell onClick={(e) => e.stopPropagation()}>
                                    <input
                                      type="checkbox"
                                      className="h-4 w-4 accent-primary"
                                      checked={marcado}
                                      onChange={() => toggleSel(c)}
                                      aria-label="Seleccionar CFDI"
                                    />
                                  </TableCell>
                                  <TableCell>
                                    <Badge variant={info.variant} title={info.hint}>
                                      {info.label}
                                    </Badge>
                                  </TableCell>
                                  <TableCell className="whitespace-nowrap">
                                    {formatDate(c.fecha)}
                                    <span className="block text-xs text-muted-foreground">
                                      {c.dias === 0 ? "mismo día" : `${c.dias} días ${c.pagado_despues ? "antes del pago" : "después del pago"}`}
                                    </span>
                                  </TableCell>
                                  <TableCell>
                                    <span className="block max-w-56 truncate" title={c.nombre_contraparte}>
                                      {c.contraparte_en_concepto && (
                                        <span className="mr-1 text-[color:var(--status-good)]" title="El nombre o RFC aparece en el concepto del banco">
                                          ●
                                        </span>
                                      )}
                                      {c.nombre_contraparte}
                                    </span>
                                    <span className="font-mono text-xs text-muted-foreground">{c.rfc_contraparte}</span>
                                  </TableCell>
                                  <TableCell className="text-xs">
                                    <span className="capitalize">{c.tipo}</span>
                                    {c.metodo_pago ? ` · ${c.metodo_pago}` : ""}
                                    <span className="block font-mono text-muted-foreground" title={c.uuid_fiscal}>
                                      {c.serie_folio ?? c.uuid_fiscal.slice(0, 8)}
                                    </span>
                                  </TableCell>
                                  <TableCell className="text-right tabular-nums">
                                    {formatMoney2(c.saldo)}
                                    {Math.abs(c.saldo - c.total) > TOL && (
                                      <span
                                        className="block text-xs text-muted-foreground"
                                        title={`REP ${formatMoney2(c.pagado_rep)} · otros movimientos ${formatMoney2(c.ligado_otros)}`}
                                      >
                                        de {formatMoney2(c.total)}
                                      </span>
                                    )}
                                  </TableCell>
                                  <TableCell className="text-right" onClick={(e) => e.stopPropagation()}>
                                    {marcado ? (
                                      <Input
                                        type="number"
                                        step="0.01"
                                        min="0.01"
                                        max={c.saldo}
                                        className="ml-auto h-8 w-32 text-right tabular-nums"
                                        value={sel[c.cfdi_id]}
                                        onChange={(e) => setSel({ ...sel, [c.cfdi_id]: Number(e.target.value) })}
                                      />
                                    ) : (
                                      <span className="text-xs text-muted-foreground">{formatMoney2(c.importe_sugerido)}</span>
                                    )}
                                  </TableCell>
                                  <TableCell onClick={(e) => e.stopPropagation()}>
                                    <Button
                                      size="sm"
                                      variant="ghost"
                                      title="Ligar solo este CFDI"
                                      onClick={() => ligarSeleccion([c.cfdi_id])}
                                      disabled={accionLoading}
                                    >
                                      <Link2 className="h-4 w-4" />
                                    </Button>
                                  </TableCell>
                                </TableRow>
                              );
                            })}
                          </TableBody>
                        </Table>
                      </div>
                    )}

                    <div className="flex flex-wrap items-center justify-between gap-2 rounded-md border p-2 text-sm">
                      <p>
                        Falta explicar <strong className="tabular-nums">{formatMoney2(restante)}</strong>
                        {Object.keys(sel).length > 0 && (
                          <>
                            {" "}
                            · seleccionados {Object.keys(sel).length} por <strong className="tabular-nums">{formatMoney2(sumaSel)}</strong> · después quedará{" "}
                            <strong
                              className={cn(
                                "tabular-nums",
                                Math.abs(restanteTrasSel) <= TOL
                                  ? "text-[color:var(--status-good)]"
                                  : restanteTrasSel < 0
                                    ? "text-[color:var(--status-critical)]"
                                    : "",
                              )}
                            >
                              {formatMoney2(restanteTrasSel)}
                            </strong>
                          </>
                        )}
                      </p>
                      <Button
                        onClick={() => ligarSeleccion()}
                        disabled={accionLoading || Object.keys(sel).length === 0 || restanteTrasSel < -TOL || Object.values(sel).some((v) => !(v > 0))}
                      >
                        <Link2 className="mr-2 h-4 w-4" /> Ligar {Object.keys(sel).length > 1 ? `${Object.keys(sel).length} CFDI` : "seleccionado"}
                      </Button>
                    </div>
                  </div>
                )}

                {/* Ignorar / volver a pendiente */}
                {movSel.ligas.length === 0 && (
                  <div className="flex items-end gap-2 border-t pt-3">
                    <div className="flex-1 space-y-1.5">
                      <Label>Nota (para ignorar)</Label>
                      <Input placeholder="Comisión bancaria, traspaso entre cuentas…" value={notaIgnorar} onChange={(e) => setNotaIgnorar(e.target.value)} />
                    </div>
                    {movSel.estado === "ignorado" ? (
                      <Button variant="outline" onClick={() => accion("desconciliar")} disabled={accionLoading}>
                        <CheckCircle2 className="mr-2 h-4 w-4" /> Volver a pendiente
                      </Button>
                    ) : (
                      <Button variant="outline" onClick={() => accion("ignorar", { body: { nota: notaIgnorar || null } })} disabled={accionLoading}>
                        <XCircle className="mr-2 h-4 w-4" /> Ignorar
                      </Button>
                    )}
                  </div>
                )}
                {errorAccion && <p className="text-sm text-destructive">{errorAccion}</p>}
              </div>
            </>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}

function fmtN(v: number | null | undefined) {
  return v == null ? "—" : formatMoney2(v);
}

function Columna({ titulo, sub, children }: { titulo: string; sub?: string; children: React.ReactNode }) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">{titulo}</CardTitle>
        {sub && <p className="text-xs text-muted-foreground">{sub}</p>}
      </CardHeader>
      <CardContent>
        <dl className="space-y-1.5 text-sm">{children}</dl>
      </CardContent>
    </Card>
  );
}

function Fila({ k, v, strong, muted }: { k: string; v: string; strong?: boolean; muted?: boolean }) {
  return (
    <div className={cn("flex items-baseline justify-between gap-3", muted && "text-muted-foreground")}>
      <dt className={cn(!muted && "text-muted-foreground")}>{k}</dt>
      <dd className={cn("text-right tabular-nums", strong && "font-semibold")}>{v}</dd>
    </div>
  );
}

function Dif({ k, v, hint }: { k: string; v: number | null; hint?: string }) {
  const ok = v != null && Math.abs(v) < 1;
  return (
    <div className="rounded-md border p-3">
      <p className="text-xs text-muted-foreground">{k}</p>
      <p
        className={cn(
          "text-lg font-semibold tabular-nums",
          v == null ? "text-muted-foreground" : ok ? "text-[color:var(--status-good)]" : "text-[color:var(--status-critical)]",
        )}
      >
        {v == null ? "sin declarar" : formatMoney2(v)}
      </p>
      {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
    </div>
  );
}

function Campo({ label, value, onChange }: { label: string; value: number | null | undefined; onChange: (v: number | null | string) => void }) {
  return (
    <div className="space-y-1.5">
      <Label>{label}</Label>
      <Input type="number" step="0.01" value={value ?? ""} onChange={(e) => onChange(e.target.value === "" ? null : Number(e.target.value))} />
    </div>
  );
}
