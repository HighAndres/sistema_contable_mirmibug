"use client";

import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";

export const MESES_LARGO = [
  "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
  "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
];

interface Props {
  anio: number;
  mes: number | null; // null = anual
  anios: number[];
  onChange: (anio: number, mes: number | null) => void;
  /** Si es false no se muestra el toggle mensual/anual (ISR siempre es "hasta el mes"). */
  permitirAnual?: boolean;
  etiquetaMes?: string;
}

export function PeriodoSelector({ anio, mes, anios, onChange, permitirAnual = true, etiquetaMes = "Mes" }: Props) {
  const listaAnios = anios.includes(anio) ? anios : [anio, ...anios];
  return (
    <div className="flex flex-wrap items-center gap-2">
      {permitirAnual && (
        <Tabs value={mes === null ? "anual" : "mensual"} onValueChange={(v) => onChange(anio, v === "anual" ? null : (mes ?? new Date().getMonth() + 1))}>
          <TabsList>
            <TabsTrigger value="mensual">Mensual</TabsTrigger>
            <TabsTrigger value="anual">Anual</TabsTrigger>
          </TabsList>
        </Tabs>
      )}
      <Select value={String(anio)} onValueChange={(v) => onChange(Number(v), mes)}>
        <SelectTrigger className="w-[110px]"><SelectValue /></SelectTrigger>
        <SelectContent>
          {listaAnios.map((a) => (
            <SelectItem key={a} value={String(a)}>{a}</SelectItem>
          ))}
        </SelectContent>
      </Select>
      {mes !== null && (
        <Select value={String(mes)} onValueChange={(v) => onChange(anio, Number(v))}>
          <SelectTrigger className="w-[150px]"><SelectValue placeholder={etiquetaMes} /></SelectTrigger>
          <SelectContent>
            {MESES_LARGO.map((m, i) => (
              <SelectItem key={m} value={String(i + 1)}>{m}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      )}
    </div>
  );
}
