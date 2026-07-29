"use client";

import { useEffect, useState } from "react";
import { Download } from "lucide-react";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { useEmpresa } from "@/components/empresa-provider";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { apiFetch } from "@/lib/api";
import { exportarExcel } from "@/lib/export-xlsx";
import { formatMes, formatMoney } from "@/lib/format";
import type { MesMonto, TopContraparte } from "@/lib/types";

export default function ReportesPage() {
  const { empresaActiva } = useEmpresa();
  const [mensual, setMensual] = useState<MesMonto[]>([]);
  const [topProveedores, setTopProveedores] = useState<TopContraparte[]>([]);
  const [topClientes, setTopClientes] = useState<TopContraparte[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!empresaActiva) return;
    setLoading(true);
    Promise.all([
      apiFetch<MesMonto[]>("/reports/mensual?meses=12"),
      apiFetch<TopContraparte[]>("/reports/top-proveedores"),
      apiFetch<TopContraparte[]>("/reports/top-clientes"),
    ])
      .then(([m, prov, cli]) => {
        setMensual(m);
        setTopProveedores(prov);
        setTopClientes(cli);
      })
      .finally(() => setLoading(false));
  }, [empresaActiva]);

  if (!empresaActiva) return null;
  if (loading) return <p className="text-sm text-muted-foreground">Cargando reportes...</p>;

  const chartData = mensual.map((m) => ({
    label: formatMes(m.mes),
    utilidad: m.ingresos - m.egresos,
  }));

  function exportar() {
    exportarExcel(`nubinox-reportes-${empresaActiva!.empresa.rfc}`, {
      Mensual: mensual.map((m) => ({
        Mes: m.mes,
        Ingresos: m.ingresos,
        Egresos: m.egresos,
        Utilidad: m.ingresos - m.egresos,
      })),
      "Top clientes": topClientes.map((c) => ({ RFC: c.rfc, Cliente: c.nombre, Monto: c.monto_total, CFDIs: c.num_cfdis })),
      "Top proveedores": topProveedores.map((p) => ({
        RFC: p.rfc,
        Proveedor: p.nombre,
        Monto: p.monto_total,
        CFDIs: p.num_cfdis,
      })),
    });
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Reportes</h1>
        <Button variant="outline" onClick={exportar}>
          <Download /> Exportar a Excel
        </Button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Tendencia de utilidad</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData}>
                <CartesianGrid vertical={false} stroke="var(--chart-grid)" />
                <XAxis dataKey="label" stroke="var(--chart-axis)" fontSize={12} tickLine={false} axisLine={false} />
                <YAxis
                  stroke="var(--chart-axis)"
                  fontSize={12}
                  tickLine={false}
                  axisLine={false}
                  tickFormatter={(v) => formatMoney(Number(v))}
                  width={90}
                />
                <Tooltip formatter={(value: number) => formatMoney(value)} />
                <Legend />
                <Line
                  type="monotone"
                  dataKey="utilidad"
                  name="Utilidad"
                  stroke="var(--chart-series-1)"
                  strokeWidth={2}
                  dot={{ r: 3 }}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Top clientes</CardTitle>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Cliente</TableHead>
                  <TableHead className="text-right">Monto</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {topClientes.map((c) => (
                  <TableRow key={c.rfc}>
                    <TableCell className="max-w-56 truncate">{c.nombre}</TableCell>
                    <TableCell className="text-right tabular-nums">{formatMoney(c.monto_total)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Top proveedores</CardTitle>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Proveedor</TableHead>
                  <TableHead className="text-right">Monto</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {topProveedores.map((p) => (
                  <TableRow key={p.rfc}>
                    <TableCell className="max-w-56 truncate">{p.nombre}</TableCell>
                    <TableCell className="text-right tabular-nums">{formatMoney(p.monto_total)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
