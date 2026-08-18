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
import type { DesgloseIva, IvaPeriodo } from "@/lib/types";

const DESCRIPCION: Record<string, string> = {
  PUE: "Facturas pagadas en una sola exhibición: el IVA se causa/acredita al emitirse.",
  REP: "Complementos de pago: el IVA de facturas PPD se causa/acredita cuando efectivamente se cobra o paga.",
  "PPD pendiente": "Facturas en parcialidades sin complemento de pago: todavía NO entra al cálculo (cuentas por cobrar / pagar).",
  "No considerados": "Canceladas o en proceso de cancelación: excluidas del cálculo.",
};

export default function IvaPage() {
  const { empresaActiva } = useEmpresa();
  const hoy = new Date();
  const [anio, setAnio] = useState(hoy.getFullYear());
  const [mes, setMes] = useState<number | null>(hoy.getMonth() + 1);
  const [data, setData] = useState<IvaPeriodo | null>(null);
  const [loading, setLoading] = useState(true);

  const cargar = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ anio: String(anio) });
      if (mes) params.set("mes", String(mes));
      setData(await apiFetch<IvaPeriodo>(`/impuestos/iva?${params}`));
    } finally {
      setLoading(false);
    }
  }, [anio, mes]);

  useEffect(() => {
    if (empresaActiva) void cargar();
  }, [empresaActiva, cargar]);

  function exportar() {
    if (!data) return;
    const fila = (lado: string) => (f: DesgloseIva) => ({
      Lado: lado,
      Concepto: f.concepto,
      "# CFDIs": f.num_cfdis,
      Base: f.base,
      IVA: f.iva,
    });
    exportarExcel(`iva-${empresaActiva!.empresa.rfc}-${anio}${mes ? `-${String(mes).padStart(2, "0")}` : ""}`, {
      Resumen: [
        { Concepto: "IVA trasladado efectivamente cobrado", Monto: data.trasladado_cobrado },
        { Concepto: "IVA acreditable efectivamente pagado", Monto: data.acreditable_pagado },
        { Concepto: data.saldo >= 0 ? "IVA a cargo" : "IVA a favor", Monto: Math.abs(data.saldo) },
        { Concepto: "IVA facturado PPD pendiente de cobro", Monto: data.trasladado_ppd_pendiente },
        { Concepto: "IVA recibido PPD pendiente de pago", Monto: data.acreditable_ppd_pendiente },
      ],
      Desglose: [...data.emitidas.map(fila("Emitidas")), ...data.recibidas.map(fila("Recibidas"))],
    });
  }

  if (!empresaActiva) return null;
  const periodoTxt = mes ? `${MESES_LARGO[mes - 1]} ${anio}` : `Ejercicio ${anio}`;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">IVA · previa en base a flujo</h1>
          <p className="text-sm text-muted-foreground">
            Trasladado efectivamente cobrado menos acreditable efectivamente pagado, con los CFDI de la bóveda. Úsalo para
            comparar contra lo declarado antes del cierre.
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
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <StatTile label="IVA trasladado (cobrado)" value={formatMoney2(data.trasladado_cobrado)} hint={`${periodoTxt} · PUE + REP emitidos`} />
            <StatTile label="IVA acreditable (pagado)" value={formatMoney2(data.acreditable_pagado)} hint="PUE + REP recibidos" />
            <StatTile
              label={data.saldo >= 0 ? "IVA a cargo" : "IVA a favor"}
              value={formatMoney2(Math.abs(data.saldo))}
              tone={data.saldo >= 0 ? "critical" : "good"}
              hint={data.saldo >= 0 ? "Trasladado − acreditable > 0" : "Acreditable mayor al trasladado"}
            />
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <StatTile label="IVA facturado PPD pendiente de cobro" value={formatMoney2(data.trasladado_ppd_pendiente)} hint="Cuentas por cobrar: se causará al recibir el pago (REP)" />
            <StatTile label="IVA recibido PPD pendiente de pago" value={formatMoney2(data.acreditable_ppd_pendiente)} hint="Cuentas por pagar: se acreditará al pagar (REP)" />
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <TablaDesglose titulo="Emitidas (IVA trasladado)" filas={data.emitidas} loading={loading} />
            <TablaDesglose titulo="Recibidas (IVA acreditable)" filas={data.recibidas} loading={loading} />
          </div>

          <p className="text-xs text-muted-foreground">
            Cálculo estimativo con los CFDI sincronizados: no incluye retenciones de IVA, saldos a favor de periodos
            anteriores, IVA de importación pagado en pedimentos ni proporción de acreditamiento. Los REP se consideran
            cobrados/pagados en su fecha de emisión.
          </p>
        </>
      )}
    </div>
  );
}

function TablaDesglose({ titulo, filas, loading }: { titulo: string; filas: DesgloseIva[]; loading: boolean }) {
  const consideradas = filas.filter((f) => f.concepto === "PUE" || f.concepto === "REP");
  const totalIva = consideradas.reduce((a, f) => a + f.iva, 0);
  const totalBase = consideradas.reduce((a, f) => a + f.base, 0);
  const totalN = consideradas.reduce((a, f) => a + f.num_cfdis, 0);
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">{titulo}</CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Tipo</TableHead>
              <TableHead className="text-right"># CFDIs</TableHead>
              <TableHead className="text-right">Base</TableHead>
              <TableHead className="text-right">IVA</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody className={loading ? "opacity-50" : ""}>
            {filas.map((f) => (
              <TableRow key={f.concepto} className={f.concepto === "PPD pendiente" || f.concepto === "No considerados" ? "text-muted-foreground" : ""}>
                <TableCell>
                  <p className="font-medium">{f.concepto}</p>
                  <p className="text-xs text-muted-foreground">{DESCRIPCION[f.concepto]}</p>
                </TableCell>
                <TableCell className="text-right tabular-nums">{f.num_cfdis}</TableCell>
                <TableCell className="text-right tabular-nums">{formatMoney2(f.base)}</TableCell>
                <TableCell className="text-right tabular-nums">{formatMoney2(f.iva)}</TableCell>
              </TableRow>
            ))}
            <TableRow className="font-semibold">
              <TableCell>Total considerado (PUE + REP)</TableCell>
              <TableCell className="text-right tabular-nums">{totalN}</TableCell>
              <TableCell className="text-right tabular-nums">{formatMoney2(totalBase)}</TableCell>
              <TableCell className="text-right tabular-nums">{formatMoney2(totalIva)}</TableCell>
            </TableRow>
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}
