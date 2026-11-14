"use client";

import { useCallback, useEffect, useState } from "react";
import { Download } from "lucide-react";

import { useEmpresa } from "@/components/empresa-provider";
import { MESES_LARGO, PeriodoSelector } from "@/components/impuestos/periodo-selector";
import { StatTile } from "@/components/stat-tile";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { apiFetch } from "@/lib/api";
import { exportarExcel } from "@/lib/export-xlsx";
import { formatMoney2 } from "@/lib/format";
import type { IsnPeriodo } from "@/lib/types";

export default function IsnPage() {
  const { empresaActiva } = useEmpresa();
  const hoy = new Date();
  const [anio, setAnio] = useState(hoy.getFullYear());
  const [mes, setMes] = useState<number | null>(hoy.getMonth() + 1);
  const [data, setData] = useState<IsnPeriodo | null>(null);
  const [loading, setLoading] = useState(true);

  const cargar = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ anio: String(anio) });
      if (mes) params.set("mes", String(mes));
      setData(await apiFetch<IsnPeriodo>(`/impuestos/isn?${params}`));
    } finally {
      setLoading(false);
    }
  }, [anio, mes]);

  useEffect(() => {
    if (empresaActiva) void cargar();
  }, [empresaActiva, cargar]);

  function exportar() {
    if (!data) return;
    exportarExcel(`isn-${empresaActiva!.empresa.rfc}-${anio}${mes ? `-${String(mes).padStart(2, "0")}` : ""}`, {
      ISN: data.filas.map((f) => ({
        Entidad: f.entidad_nombre,
        Clave: f.entidad_codigo ?? "",
        Recibos: f.recibos,
        Percepciones: f.percepciones,
        Deducciones: f.deducciones,
        "Otros pagos": f.otros_pagos,
        "Base gravable": f.base,
        "Tasa %": f.tasa != null ? f.tasa * 100 : "",
        ISN: f.isn,
      })),
    });
  }

  if (!empresaActiva) return null;
  const periodoTxt = mes ? `${MESES_LARGO[mes - 1]} ${anio}` : `Ejercicio ${anio}`;
  const recibos = data?.filas.reduce((a, f) => a + f.recibos, 0) ?? 0;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Nóminas · ISN</h1>
          <p className="text-sm text-muted-foreground">
            Impuesto Sobre Nóminas (estatal): base gravable por entidad federativa, con los recibos de nómina pagados en el periodo, por la tasa de cada
            entidad.
          </p>
        </div>
        <Button variant="outline" onClick={exportar} disabled={!data}>
          <Download className="mr-2 h-4 w-4" /> Exportar a Excel
        </Button>
      </div>

      <PeriodoSelector
        anio={anio}
        mes={mes}
        anios={data?.anios_disponibles ?? [anio]}
        onChange={(a, m) => {
          setAnio(a);
          setMes(m);
        }}
      />

      {data && (
        <>
          <div className="grid gap-3 sm:grid-cols-3">
            <StatTile label="Recibos de nómina" value={String(recibos)} hint={periodoTxt} />
            <StatTile label="Base gravable (percepciones)" value={formatMoney2(data.total_base)} hint="Gravadas + exentas de los recibos del periodo" />
            <StatTile
              label="ISN estimado"
              value={formatMoney2(data.total_isn)}
              tone={data.total_isn > 0 ? "critical" : undefined}
              hint="Suma de todas las entidades"
            />
          </div>

          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-base">Por entidad federativa</CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Entidad</TableHead>
                    <TableHead className="text-right">Recibos</TableHead>
                    <TableHead className="text-right">Percepciones</TableHead>
                    <TableHead className="text-right">Deducciones</TableHead>
                    <TableHead className="text-right">Otros pagos</TableHead>
                    <TableHead className="text-right">Base gravable</TableHead>
                    <TableHead className="text-right">Tasa</TableHead>
                    <TableHead className="text-right">ISN</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody className={loading ? "opacity-50" : ""}>
                  {data.filas.map((f) => (
                    <TableRow key={f.entidad_codigo ?? "sin"}>
                      <TableCell>
                        <p className="font-medium">{f.entidad_nombre}</p>
                        {f.entidad_codigo && <p className="font-mono text-xs text-muted-foreground">{f.entidad_codigo}</p>}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">{f.recibos}</TableCell>
                      <TableCell className="text-right tabular-nums">{formatMoney2(f.percepciones)}</TableCell>
                      <TableCell className="text-right tabular-nums text-muted-foreground">{formatMoney2(f.deducciones)}</TableCell>
                      <TableCell className="text-right tabular-nums text-muted-foreground">{formatMoney2(f.otros_pagos)}</TableCell>
                      <TableCell className="text-right tabular-nums">{formatMoney2(f.base)}</TableCell>
                      <TableCell className="text-right tabular-nums">{f.tasa != null ? `${+(f.tasa * 100).toFixed(4)}%` : "—"}</TableCell>
                      <TableCell className="text-right font-medium tabular-nums">{formatMoney2(f.isn)}</TableCell>
                    </TableRow>
                  ))}
                  {data.filas.length === 0 && (
                    <TableRow>
                      <TableCell colSpan={8} className="py-8 text-center text-muted-foreground">
                        Sin recibos de nómina pagados en {periodoTxt}.
                      </TableCell>
                    </TableRow>
                  )}
                  {data.filas.length > 0 && (
                    <TableRow className="font-semibold">
                      <TableCell>Total</TableCell>
                      <TableCell className="text-right tabular-nums">{recibos}</TableCell>
                      <TableCell className="text-right tabular-nums">{formatMoney2(data.filas.reduce((a, f) => a + f.percepciones, 0))}</TableCell>
                      <TableCell className="text-right tabular-nums">{formatMoney2(data.filas.reduce((a, f) => a + f.deducciones, 0))}</TableCell>
                      <TableCell className="text-right tabular-nums">{formatMoney2(data.filas.reduce((a, f) => a + f.otros_pagos, 0))}</TableCell>
                      <TableCell className="text-right tabular-nums">{formatMoney2(data.total_base)}</TableCell>
                      <TableCell />
                      <TableCell className="text-right tabular-nums">{formatMoney2(data.total_isn)}</TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </CardContent>
          </Card>

          {data.advertencias.map((a) => (
            <p key={a} className="text-xs text-[color:var(--status-warning)]">
              {a}
            </p>
          ))}
          <p className="text-xs text-muted-foreground">
            Cálculo estimativo: la base usa el total de percepciones de los recibos (la ley de cada estado afina qué conceptos entran, exenciones y sobretasas).
            Las tasas por entidad son referenciales 2026 y se ajustan en el sistema cuando cambia una ley estatal — valida la tasa de cada entidad donde haya
            nómina antes de declarar.
          </p>
        </>
      )}
    </div>
  );
}
