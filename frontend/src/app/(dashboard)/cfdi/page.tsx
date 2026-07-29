"use client";

import { useCallback, useEffect, useState } from "react";
import { Download, RefreshCw } from "lucide-react";

import { useEmpresa } from "@/components/empresa-provider";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { apiFetch } from "@/lib/api";
import { exportarExcel } from "@/lib/export-xlsx";
import { PERM, can } from "@/lib/permissions";
import { formatDate, formatMoney } from "@/lib/format";
import type { CfdiDetalle, CfdiPage } from "@/lib/types";

const SEVERIDAD_VARIANT = {
  alta: "destructive",
  media: "warning",
  baja: "success",
} as const;

export default function CfdiPageRoute() {
  const { empresaActiva } = useEmpresa();
  const [page, setPage] = useState<CfdiPage | null>(null);
  const [tipo, setTipo] = useState<string>("todos");
  const [direccion, setDireccion] = useState<string>("todos");
  const [loading, setLoading] = useState(true);
  const [sincronizando, setSincronizando] = useState(false);
  const [detalle, setDetalle] = useState<CfdiDetalle | null>(null);

  const cargar = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ limit: "100" });
      if (tipo !== "todos") params.set("tipo", tipo);
      if (direccion !== "todos") params.set("direccion", direccion);
      const data = await apiFetch<CfdiPage>(`/cfdi?${params.toString()}`);
      setPage(data);
    } finally {
      setLoading(false);
    }
  }, [tipo, direccion]);

  useEffect(() => {
    if (empresaActiva) void cargar();
  }, [empresaActiva, cargar]);

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
    const data = await apiFetch<CfdiDetalle>(`/cfdi/${id}`);
    setDetalle(data);
  }

  function exportar() {
    if (!page) return;
    exportarExcel(`nubinox-cfdi-${empresaActiva!.empresa.rfc}`, {
      CFDI: page.items.map((c) => ({
        Fecha: c.fecha,
        Tipo: c.tipo,
        Direccion: c.direccion,
        "RFC emisor": c.rfc_emisor,
        Emisor: c.nombre_emisor,
        "RFC receptor": c.rfc_receptor,
        Receptor: c.nombre_receptor,
        Subtotal: c.subtotal,
        IVA: c.iva,
        Total: c.total,
        Estatus: c.estatus,
      })),
    });
  }

  if (!empresaActiva) return null;
  const permisos = empresaActiva.permisos;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold">CFDI</h1>
        <div className="flex gap-2">
          <Button variant="outline" onClick={exportar} disabled={!page?.items.length}>
            <Download /> Exportar a Excel
          </Button>
          {can(permisos, PERM.SAT_SINCRONIZAR) && (
            <Button onClick={sincronizar} disabled={sincronizando}>
              <RefreshCw className={sincronizando ? "animate-spin" : ""} />
              {sincronizando ? "Sincronizando..." : "Sincronizar con SAT"}
            </Button>
          )}
        </div>
      </div>

      <div className="flex flex-wrap gap-3">
        <Select value={tipo} onValueChange={setTipo}>
          <SelectTrigger className="w-44">
            <SelectValue placeholder="Tipo" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="todos">Todos los tipos</SelectItem>
            <SelectItem value="ingreso">Ingreso</SelectItem>
            <SelectItem value="egreso">Egreso</SelectItem>
            <SelectItem value="pago">Pago</SelectItem>
          </SelectContent>
        </Select>
        <Select value={direccion} onValueChange={setDireccion}>
          <SelectTrigger className="w-44">
            <SelectValue placeholder="Dirección" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="todos">Emitidos y recibidos</SelectItem>
            <SelectItem value="emitido">Emitidos</SelectItem>
            <SelectItem value="recibido">Recibidos</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Fecha</TableHead>
                <TableHead>Tipo</TableHead>
                <TableHead>Emisor</TableHead>
                <TableHead>Receptor</TableHead>
                <TableHead className="text-right">Total</TableHead>
                <TableHead>Estatus</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {loading && (
                <TableRow>
                  <TableCell colSpan={6} className="text-center text-muted-foreground">
                    Cargando...
                  </TableCell>
                </TableRow>
              )}
              {!loading &&
                page?.items.map((c) => (
                  <TableRow key={c.id} className="cursor-pointer" onClick={() => verDetalle(c.id)}>
                    <TableCell>{formatDate(c.fecha)}</TableCell>
                    <TableCell className="capitalize">{c.tipo}</TableCell>
                    <TableCell className="max-w-48 truncate">{c.nombre_emisor}</TableCell>
                    <TableCell className="max-w-48 truncate">{c.nombre_receptor}</TableCell>
                    <TableCell className="text-right tabular-nums">{formatMoney(c.total)}</TableCell>
                    <TableCell>
                      <Badge variant={c.estatus === "vigente" ? "secondary" : "destructive"}>{c.estatus}</Badge>
                    </TableCell>
                  </TableRow>
                ))}
              {!loading && page?.items.length === 0 && (
                <TableRow>
                  <TableCell colSpan={6} className="text-center text-muted-foreground">
                    Sin CFDIs. Usa &quot;Sincronizar con SAT&quot; para traer datos.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <Dialog open={!!detalle} onOpenChange={(open) => !open && setDetalle(null)}>
        <DialogContent className="max-w-2xl">
          {detalle && (
            <>
              <DialogHeader>
                <DialogTitle>CFDI {detalle.uuid_fiscal}</DialogTitle>
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

                {detalle.alertas.length > 0 && (
                  <div className="space-y-2">
                    <p className="font-medium">Alertas</p>
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
                        <TableHead className="text-right">Importe</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {detalle.conceptos.map((c) => (
                        <TableRow key={c.id}>
                          <TableCell>{c.descripcion}</TableCell>
                          <TableCell className="text-right">{c.cantidad}</TableCell>
                          <TableCell className="text-right tabular-nums">{formatMoney(c.importe)}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>

                <div className="flex justify-end gap-6 text-right">
                  <div>
                    <p className="text-muted-foreground">Subtotal</p>
                    <p className="tabular-nums">{formatMoney(detalle.subtotal)}</p>
                  </div>
                  <div>
                    <p className="text-muted-foreground">IVA</p>
                    <p className="tabular-nums">{formatMoney(detalle.iva)}</p>
                  </div>
                  <div>
                    <p className="text-muted-foreground">Total</p>
                    <p className="font-semibold tabular-nums">{formatMoney(detalle.total)}</p>
                  </div>
                </div>
              </div>
            </>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
