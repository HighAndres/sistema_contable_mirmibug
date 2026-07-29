"use client";

import { useEffect, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { useEmpresa } from "@/components/empresa-provider";
import { StatTile } from "@/components/stat-tile";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { apiFetch } from "@/lib/api";
import { formatMes, formatMoney } from "@/lib/format";
import type { DashboardKPIs, MesMonto, TopContraparte } from "@/lib/types";

export default function DashboardPage() {
  const { empresaActiva } = useEmpresa();
  const [kpis, setKpis] = useState<DashboardKPIs | null>(null);
  const [mensual, setMensual] = useState<MesMonto[]>([]);
  const [topClientes, setTopClientes] = useState<TopContraparte[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!empresaActiva) return;
    setLoading(true);
    Promise.all([
      apiFetch<DashboardKPIs>("/reports/dashboard"),
      apiFetch<MesMonto[]>("/reports/mensual"),
      apiFetch<TopContraparte[]>("/reports/top-clientes"),
    ])
      .then(([k, m, c]) => {
        setKpis(k);
        setMensual(m);
        setTopClientes(c);
      })
      .finally(() => setLoading(false));
  }, [empresaActiva]);

  if (!empresaActiva) return null;
  if (loading || !kpis) return <p className="text-sm text-muted-foreground">Cargando dashboard...</p>;

  const chartData = mensual.map((m) => ({ ...m, label: formatMes(m.mes) }));

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Dashboard fiscal</h1>
        <p className="text-sm text-muted-foreground">{empresaActiva.empresa.razon_social}</p>
      </div>

      <div className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-5">
        <StatTile label="Ingresos" value={formatMoney(kpis.ingresos_total)} />
        <StatTile label="Egresos" value={formatMoney(kpis.egresos_total)} />
        <StatTile
          label="Utilidad"
          value={formatMoney(kpis.utilidad)}
          tone={kpis.utilidad >= 0 ? "good" : "critical"}
        />
        <StatTile label="IVA por pagar" value={formatMoney(kpis.iva_por_pagar)} />
        <StatTile label="ISR estimado" value={formatMoney(kpis.isr_estimado)} />
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle className="text-base">Ingresos vs egresos (últimos meses)</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="viz-root h-72">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chartData} barGap={4}>
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
                  <Bar dataKey="ingresos" name="Ingresos" fill="var(--chart-series-1)" radius={[4, 4, 0, 0]} />
                  <Bar dataKey="egresos" name="Egresos" fill="var(--chart-series-2)" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Alertas de validación</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <p className="text-sm text-muted-foreground">
              {kpis.cfdis_con_alertas} de {kpis.cfdis_vigentes} CFDIs vigentes con alguna alerta
            </p>
            <div className="flex flex-wrap gap-2">
              <Badge variant="destructive">{kpis.alertas_altas} altas</Badge>
              <Badge variant="warning">{kpis.alertas_medias} medias</Badge>
              <Badge variant="success">{kpis.alertas_bajas} bajas</Badge>
            </div>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Top clientes</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>RFC</TableHead>
                <TableHead>Cliente</TableHead>
                <TableHead className="text-right">CFDIs</TableHead>
                <TableHead className="text-right">Monto</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {topClientes.map((c) => (
                <TableRow key={c.rfc}>
                  <TableCell className="font-mono text-xs">{c.rfc}</TableCell>
                  <TableCell>{c.nombre}</TableCell>
                  <TableCell className="text-right">{c.num_cfdis}</TableCell>
                  <TableCell className="text-right tabular-nums">{formatMoney(c.monto_total)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
