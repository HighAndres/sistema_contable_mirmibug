"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { BookOpen, FileUp, Ship } from "lucide-react";

import { CargaMasivaDialog } from "@/components/carga-masiva-dialog";
import { useEmpresa } from "@/components/empresa-provider";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
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
import { ApiError, apiFetch } from "@/lib/api";
import { formatDate, formatMoney, formatNumber } from "@/lib/format";
import { PERM, can } from "@/lib/permissions";
import type { ImportarM3Response, PedimentoResumen } from "@/lib/types";

const TODOS = "__todos__";

export default function PedimentosPage() {
  const router = useRouter();
  const { empresaActiva } = useEmpresa();
  const [pedimentos, setPedimentos] = useState<PedimentoResumen[]>([]);
  const [loading, setLoading] = useState(true);
  const [filtroEstatus, setFiltroEstatus] = useState(TODOS);
  const [busqueda, setBusqueda] = useState("");

  // --- diálogo: importar M3 ---
  const [openImport, setOpenImport] = useState(false);
  const [archivo, setArchivo] = useState<File | null>(null);
  const [referencia, setReferencia] = useState("");
  const [errorImport, setErrorImport] = useState<string | null>(null);
  const [subiendo, setSubiendo] = useState(false);
  const [resultado, setResultado] = useState<ImportarM3Response | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const [openCatalogo, setOpenCatalogo] = useState(false);

  const cargar = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (filtroEstatus !== TODOS) params.set("estatus", filtroEstatus);
      if (busqueda.trim()) params.set("q", busqueda.trim());
      const qs = params.toString();
      setPedimentos(await apiFetch<PedimentoResumen[]>(`/pedimentos${qs ? `?${qs}` : ""}`));
    } finally {
      setLoading(false);
    }
  }, [filtroEstatus, busqueda]);

  useEffect(() => {
    if (empresaActiva) void cargar();
  }, [empresaActiva, cargar]);

  function resetImport() {
    setArchivo(null);
    setReferencia("");
    setErrorImport(null);
    setResultado(null);
    if (inputRef.current) inputRef.current.value = "";
  }

  async function handleImportar(e: React.FormEvent) {
    e.preventDefault();
    if (!archivo) {
      setErrorImport("Selecciona el archivo M3 (.003) del agente aduanal");
      return;
    }
    setErrorImport(null);
    setSubiendo(true);
    try {
      const form = new FormData();
      form.append("archivo", archivo);
      if (referencia.trim()) form.append("referencia", referencia.trim());
      const res = await apiFetch<ImportarM3Response>("/pedimentos/importar", { method: "POST", body: form });
      setResultado(res);
      await cargar();
    } catch (err) {
      setErrorImport(err instanceof ApiError ? err.message : "Error al importar el archivo");
    } finally {
      setSubiendo(false);
    }
  }

  if (!empresaActiva) return null;
  const puedeGestionar = can(empresaActiva.permisos, PERM.PEDIMENTOS_GESTIONAR);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Pedimentos de importación</h1>
          <p className="text-sm text-muted-foreground">
            Costeo de importación por partida: sube el archivo M3 (.003) del agente aduanal y el sistema
            calcula DTA, IGI, gastos y utilidad por pieza.
          </p>
        </div>
        {puedeGestionar && (
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" onClick={() => setOpenCatalogo(true)}>
              <BookOpen className="mr-2 h-4 w-4" />
              Catálogo claves SAT
            </Button>
            <Button
              onClick={() => {
                resetImport();
                setOpenImport(true);
              }}
            >
              <FileUp className="mr-2 h-4 w-4" />
              Importar M3 (.003)
            </Button>
            <CargaMasivaDialog
              open={openCatalogo}
              onOpenChange={setOpenCatalogo}
              titulo="Catálogo concepto → clave SAT"
              descripcion="Sube la hoja CATALOGO del papel de trabajo (columnas: Concepto, Clave SAT y opcionalmente Clave unidad). Al importar un pedimento, cada partida toma su clave por descripción; para pedimentos ya importados usa 'Aplicar claves' en el detalle."
              endpointImportar="/pedimentos/conceptos/importar"
              endpointPlantilla="/pedimentos/conceptos/plantilla"
              nombrePlantilla="plantilla_conceptos_sat.xlsx"
              etiquetaCreados="conceptos nuevos"
              etiquetaActualizados="actualizados"
            />
          </div>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <Input
          placeholder="Buscar por número, referencia o proveedor…"
          value={busqueda}
          onChange={(e) => setBusqueda(e.target.value)}
          className="w-72"
        />
        <Select value={filtroEstatus} onValueChange={setFiltroEstatus}>
          <SelectTrigger className="w-44">
            <SelectValue placeholder="Estatus" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={TODOS}>Todos los estatus</SelectItem>
            <SelectItem value="borrador">Borrador</SelectItem>
            <SelectItem value="aplicado">Aplicado a inventario</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <Card>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Pedimento</TableHead>
                  <TableHead>Referencia</TableHead>
                  <TableHead>Fecha pago</TableHead>
                  <TableHead>Proveedor</TableHead>
                  <TableHead className="text-right">Partidas</TableHead>
                  <TableHead className="text-right">T.C.</TableHead>
                  <TableHead className="text-right">Valor aduana</TableHead>
                  <TableHead className="text-right">DTA</TableHead>
                  <TableHead className="text-right">IGI</TableHead>
                  <TableHead className="text-right">IVA imp.</TableHead>
                  <TableHead>Estatus</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {loading ? (
                  <TableRow>
                    <TableCell colSpan={11} className="py-8 text-center text-muted-foreground">
                      Cargando…
                    </TableCell>
                  </TableRow>
                ) : pedimentos.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={11} className="py-10 text-center text-muted-foreground">
                      <Ship className="mx-auto mb-2 h-8 w-8 opacity-40" />
                      Aún no hay pedimentos. {puedeGestionar && "Importa el primer archivo M3 para empezar."}
                    </TableCell>
                  </TableRow>
                ) : (
                  pedimentos.map((p) => (
                    <TableRow
                      key={p.id}
                      className="cursor-pointer"
                      onClick={() => router.push(`/pedimentos/${p.id}`)}
                    >
                      <TableCell className="font-mono text-sm font-medium">{p.numero_completo}</TableCell>
                      <TableCell>{p.referencia ?? <span className="text-muted-foreground">—</span>}</TableCell>
                      <TableCell>{p.fecha_pago ? formatDate(p.fecha_pago) : "—"}</TableCell>
                      <TableCell className="max-w-[220px] truncate" title={p.proveedor_nombre ?? ""}>
                        {p.proveedor_nombre ?? "—"}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">{p.num_partidas}</TableCell>
                      <TableCell className="text-right tabular-nums">{formatNumber(p.tipo_cambio)}</TableCell>
                      <TableCell className="text-right tabular-nums">{formatMoney(p.valor_aduana_total)}</TableCell>
                      <TableCell className="text-right tabular-nums">{formatMoney(p.dta)}</TableCell>
                      <TableCell className="text-right tabular-nums">{formatMoney(p.igi_total)}</TableCell>
                      <TableCell className="text-right tabular-nums">{formatMoney(p.iva_total)}</TableCell>
                      <TableCell>
                        <Badge variant={p.estatus === "aplicado" ? "success" : "secondary"}>
                          {p.estatus === "aplicado" ? "Aplicado" : "Borrador"}
                        </Badge>
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>

      <Dialog
        open={openImport}
        onOpenChange={(o) => {
          setOpenImport(o);
          if (!o) resetImport();
        }}
      >
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Importar pedimento desde M3</DialogTitle>
            <DialogDescription>
              El archivo M3 (extensión .003, .004…) es el que entrega el agente aduanal con la validación del
              pedimento. Trae encabezado, contribuciones y todas las partidas: no hace falta capturar nada más.
            </DialogDescription>
          </DialogHeader>

          {resultado ? (
            <div className="space-y-3">
              <div className="rounded-md border p-3 text-sm">
                <p className="font-medium">
                  Pedimento <span className="font-mono">{resultado.pedimento.numero_completo}</span> importado
                </p>
                <p className="text-muted-foreground">
                  {resultado.pedimento.num_partidas} partidas · T.C. {formatNumber(resultado.pedimento.tipo_cambio)}{" "}
                  · Valor aduana {formatMoney(resultado.pedimento.valor_aduana_total)} · DTA{" "}
                  {formatMoney(resultado.pedimento.dta)} · IGI {formatMoney(resultado.pedimento.igi_total)} · IVA{" "}
                  {formatMoney(resultado.pedimento.iva_total)}
                </p>
              </div>
              {resultado.advertencias.length > 0 && (
                <ul className="list-disc space-y-1 rounded-md border border-amber-500/40 bg-amber-500/10 p-3 pl-7 text-sm">
                  {resultado.advertencias.map((a) => (
                    <li key={a}>{a}</li>
                  ))}
                </ul>
              )}
              <DialogFooter>
                <Button variant="outline" onClick={() => setOpenImport(false)}>
                  Cerrar
                </Button>
                <Button onClick={() => router.push(`/pedimentos/${resultado.pedimento.id}`)}>Ver costeo</Button>
              </DialogFooter>
            </div>
          ) : (
            <form onSubmit={handleImportar} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="archivo">Archivo M3</Label>
                <Input
                  id="archivo"
                  ref={inputRef}
                  type="file"
                  accept=".003,.004,.005,.006,.007,.008,.009,.001,.002,.txt,application/octet-stream"
                  onChange={(e) => setArchivo(e.target.files?.[0] ?? null)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="referencia">Referencia interna (opcional)</Label>
                <Input
                  id="referencia"
                  placeholder="p. ej. LMA26-019"
                  value={referencia}
                  onChange={(e) => setReferencia(e.target.value)}
                />
              </div>
              {errorImport && <p className="text-sm text-destructive">{errorImport}</p>}
              <DialogFooter>
                <Button type="button" variant="outline" onClick={() => setOpenImport(false)}>
                  Cancelar
                </Button>
                <Button type="submit" disabled={subiendo}>
                  {subiendo ? "Importando…" : "Importar"}
                </Button>
              </DialogFooter>
            </form>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
