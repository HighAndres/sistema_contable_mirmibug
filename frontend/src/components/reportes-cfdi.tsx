"use client";

import { useEffect, useState } from "react";
import { Download, FileSpreadsheet } from "lucide-react";

import { useEmpresa } from "@/components/empresa-provider";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ApiError, apiFetch } from "@/lib/api";
import { exportarTabla } from "@/lib/export-xlsx";
import { PERM, type Permiso, can } from "@/lib/permissions";
import type { CfdiResumen, ReporteCfdi } from "@/lib/types";

const TODOS = "__todos__";
const MESES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"];

type Formato = "general" | "comp" | "conciliacion" | "pagos" | "nomina" | "nomina_conceptos";

/** Los mismos reportes que el despacho baja hoy de su portal. Los de nómina
 * piden su propio permiso: llevan sueldos, CURP, NSS y cuenta bancaria. */
const REPORTES: {
  formato: Formato;
  titulo: string;
  ayuda: string;
  hoja: string;
  permiso?: Permiso;
}[] = [
  {
    formato: "general",
    titulo: "General",
    ayuda: "El layout del portal completo, más las columnas del papel de trabajo (deducible, concepto, cuenta contable, referencia y fecha de pago) ya resueltas.",
    hoja: "GENERAL",
  },
  {
    formato: "comp",
    titulo: "General con desglose de impuestos",
    ayuda: "Lo mismo, pero con base e importe de cada tasa de IVA e IEPS por separado, para cuadrar contra la declaración.",
    hoja: "DESGLOSE",
  },
  {
    formato: "conciliacion",
    titulo: "Conciliación",
    ayuda: "Cada factura contra lo efectivamente cobrado o pagado, con saldo insoluto y resultado.",
    hoja: "CONCILIACION",
  },
  {
    formato: "pagos",
    titulo: "Complementos de pago",
    ayuda: "Una fila por factura liquidada en cada REP, con parcialidad, saldo anterior e insoluto.",
    hoja: "PAGOS",
  },
  {
    formato: "nomina",
    titulo: "Nómina",
    ayuda: "Un recibo por fila con los datos del trabajador y los totales del periodo.",
    hoja: "NOMINA",
    permiso: PERM.NOMINA_LEER,
  },
  {
    formato: "nomina_conceptos",
    titulo: "Nómina a detalle",
    ayuda: "Una fila por percepción, deducción u otro pago del recibo.",
    hoja: "NOMINA DETALLE",
    permiso: PERM.NOMINA_LEER,
  },
];

export function ReportesCfdi() {
  const { empresaActiva } = useEmpresa();
  const hoy = new Date();
  const [anio, setAnio] = useState(String(hoy.getFullYear()));
  const [mes, setMes] = useState(TODOS);
  const [direccion, setDireccion] = useState(TODOS);
  const [anios, setAnios] = useState<number[]>([]);
  const [generando, setGenerando] = useState<Formato | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);

  useEffect(() => {
    if (!empresaActiva) return;
    apiFetch<CfdiResumen>("/cfdi/resumen")
      .then((r) => setAnios(r.anios))
      .catch(() => setAnios([]));
  }, [empresaActiva]);

  async function descargar(r: (typeof REPORTES)[number]) {
    setGenerando(r.formato);
    setAviso(null);
    try {
      const p = new URLSearchParams({ anio });
      if (mes !== TODOS) p.set("mes", mes);
      // Los de nómina y pagos ya vienen acotados por el servidor a su tipo.
      if (direccion !== TODOS && !["nomina", "nomina_conceptos", "pagos"].includes(r.formato)) p.set("direccion", direccion);

      const res = await apiFetch<ReporteCfdi>(`/cfdi/reporte/${r.formato}?${p.toString()}`);
      if (!res.filas.length) {
        setAviso("No hay CFDI en ese periodo con esos filtros.");
        return;
      }
      const periodo = mes === TODOS ? anio : `${anio}-${mes.padStart(2, "0")}`;
      exportarTabla(`nubinox-${r.formato}-${empresaActiva!.empresa.rfc}-${periodo}`, r.hoja, res.columnas, res.filas);

      const avisos = [];
      if (res.truncado) avisos.push(`Se exportaron las primeras ${res.filas.length} de ${res.total} filas; filtra por mes para bajarlo completo.`);
      // Si no se dice, el contador cree que el dato se perdió y lo busca en el XML.
      if (res.sin_dato.length) avisos.push(`Columnas que salen vacías porque aún no tomamos ese dato del XML: ${res.sin_dato.join(", ")}.`);
      setAviso(avisos.join(" ") || `Listo: ${res.filas.length} fila(s).`);
    } catch (err) {
      setAviso(err instanceof ApiError ? err.message : "No se pudo generar el reporte");
    } finally {
      setGenerando(null);
    }
  }

  if (!empresaActiva) return null;
  const permisos = empresaActiva.permisos;
  const disponibles = REPORTES.filter((r) => !r.permiso || can(permisos, r.permiso));
  const listaAnios = anios.length ? anios : [hoy.getFullYear()];

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <FileSpreadsheet className="h-4 w-4" /> Reportes de CFDI
        </CardTitle>
        <p className="text-sm text-muted-foreground">
          Con el mismo layout que el despacho baja de su portal, para pegarlos directo en el papel de trabajo.
        </p>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap items-end gap-3">
          <div className="space-y-1">
            <Label htmlFor="rep-anio">Año</Label>
            <Select value={anio} onValueChange={setAnio}>
              <SelectTrigger id="rep-anio" className="w-[120px]"><SelectValue /></SelectTrigger>
              <SelectContent>
                {listaAnios.map((a) => (
                  <SelectItem key={a} value={String(a)}>{a}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label htmlFor="rep-mes">Mes</Label>
            <Select value={mes} onValueChange={setMes}>
              <SelectTrigger id="rep-mes" className="w-[150px]"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value={TODOS}>Todo el año</SelectItem>
                {MESES.map((m, i) => (
                  <SelectItem key={m} value={String(i + 1)}>{m}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label htmlFor="rep-dir">Comprobantes</Label>
            <Select value={direccion} onValueChange={setDireccion}>
              <SelectTrigger id="rep-dir" className="w-[190px]"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value={TODOS}>Emitidos y recibidos</SelectItem>
                <SelectItem value="emitido">Emitidos (ingresos)</SelectItem>
                <SelectItem value="recibido">Recibidos (gastos)</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>

        <div className="grid gap-2 sm:grid-cols-2">
          {disponibles.map((r) => (
            <div key={r.formato} className="flex items-start justify-between gap-3 rounded-md border p-3">
              <div className="min-w-0">
                <p className="text-sm font-medium">{r.titulo}</p>
                <p className="text-xs text-muted-foreground">{r.ayuda}</p>
              </div>
              <Button variant="outline" size="sm" disabled={generando !== null} onClick={() => descargar(r)}>
                <Download className="mr-1 h-4 w-4" />
                {generando === r.formato ? "Generando..." : "Excel"}
              </Button>
            </div>
          ))}
        </div>

        {aviso && <p className="rounded-md border bg-muted/50 px-3 py-2 text-sm">{aviso}</p>}
      </CardContent>
    </Card>
  );
}
