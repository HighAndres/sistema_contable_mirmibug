"use client";

import { useEffect, useState } from "react";

import { useEmpresa } from "@/components/empresa-provider";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { apiFetch } from "@/lib/api";
import type { BitacoraEntrada } from "@/lib/types";

function formatFechaHora(iso: string): string {
  return new Intl.DateTimeFormat("es-MX", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(iso));
}

const ACCION_LABEL: Record<string, string> = {
  "empresa.creada": "Empresa creada",
  "sat.conectado": "SAT conectado",
  "sat.sincronizado": "SAT sincronizado",
  "inventario.almacen_creado": "Almacén creado",
  "inventario.producto_creado": "Producto creado",
  "inventario.movimiento": "Movimiento de inventario",
};

export default function BitacoraPage() {
  const { empresaActiva } = useEmpresa();
  const [entradas, setEntradas] = useState<BitacoraEntrada[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!empresaActiva) return;
    setLoading(true);
    apiFetch<BitacoraEntrada[]>("/bitacora?limit=200")
      .then(setEntradas)
      .finally(() => setLoading(false));
  }, [empresaActiva]);

  if (!empresaActiva) return null;

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold">Bitácora</h1>
        <p className="text-sm text-muted-foreground">
          Qué hizo cada usuario en {empresaActiva.empresa.razon_social}
        </p>
      </div>

      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Fecha</TableHead>
                <TableHead>Usuario</TableHead>
                <TableHead>Acción</TableHead>
                <TableHead>Detalle</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {loading && (
                <TableRow>
                  <TableCell colSpan={4} className="text-center text-muted-foreground">
                    Cargando...
                  </TableCell>
                </TableRow>
              )}
              {!loading &&
                entradas.map((e) => (
                  <TableRow key={e.id}>
                    <TableCell className="whitespace-nowrap text-sm text-muted-foreground">
                      {formatFechaHora(e.created_at)}
                    </TableCell>
                    <TableCell className="text-sm">{e.usuario_email}</TableCell>
                    <TableCell>
                      <Badge variant="secondary">{ACCION_LABEL[e.accion] ?? e.accion}</Badge>
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">{e.descripcion}</TableCell>
                  </TableRow>
                ))}
              {!loading && entradas.length === 0 && (
                <TableRow>
                  <TableCell colSpan={4} className="text-center text-muted-foreground">
                    Sin actividad registrada todavía.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
