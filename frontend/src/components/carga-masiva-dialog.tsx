"use client";

import { useRef, useState } from "react";
import { Download, FileUp } from "lucide-react";

import { Button } from "@/components/ui/button";
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
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ApiError, apiDownload, apiFetch } from "@/lib/api";

export interface ResultadoCarga {
  creados: number;
  actualizados: number;
  errores: { fila: number; error: string; [k: string]: unknown }[];
  [k: string]: unknown;
}

interface Props {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  titulo: string;
  descripcion: string;
  /** Endpoint POST multipart (campo `archivo`). */
  endpointImportar: string;
  /** Endpoint GET de la plantilla .xlsx (opcional). */
  endpointPlantilla?: string;
  nombrePlantilla?: string;
  etiquetaCreados?: string;
  etiquetaActualizados?: string;
  onImportado?: (r: ResultadoCarga) => void;
}

/** Diálogo genérico de carga masiva: descargar plantilla → subir xlsx/csv → ver resultado y errores por fila. */
export function CargaMasivaDialog({
  open,
  onOpenChange,
  titulo,
  descripcion,
  endpointImportar,
  endpointPlantilla,
  nombrePlantilla = "plantilla.xlsx",
  etiquetaCreados = "creados",
  etiquetaActualizados = "actualizados",
  onImportado,
}: Props) {
  const [archivo, setArchivo] = useState<File | null>(null);
  const [subiendo, setSubiendo] = useState(false);
  const [resultado, setResultado] = useState<ResultadoCarga | null>(null);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  function reset() {
    setArchivo(null);
    setResultado(null);
    setError(null);
    if (inputRef.current) inputRef.current.value = "";
  }

  async function importar() {
    if (!archivo) {
      setError("Selecciona un archivo .xlsx o .csv");
      return;
    }
    setSubiendo(true);
    setError(null);
    try {
      const form = new FormData();
      form.append("archivo", archivo);
      const r = await apiFetch<ResultadoCarga>(endpointImportar, { method: "POST", body: form });
      setResultado(r);
      onImportado?.(r);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Error al importar");
    } finally {
      setSubiendo(false);
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        onOpenChange(o);
        if (!o) reset();
      }}
    >
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>{titulo}</DialogTitle>
          <DialogDescription>{descripcion}</DialogDescription>
        </DialogHeader>

        {resultado ? (
          <div className="space-y-3 text-sm">
            <p>
              <strong>{resultado.creados}</strong> {etiquetaCreados}
              {resultado.actualizados > 0 && (
                <>
                  , <strong>{resultado.actualizados}</strong> {etiquetaActualizados}
                </>
              )}
              {resultado.errores.length > 0 ? (
                <>
                  , <strong className="text-destructive">{resultado.errores.length}</strong> fila
                  {resultado.errores.length === 1 ? "" : "s"} con error (no se aplicaron; corrígelas y vuelve a subir solo esas).
                </>
              ) : (
                "."
              )}
            </p>
            {resultado.errores.length > 0 && (
              <div className="max-h-72 overflow-auto rounded-md border">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="w-16">Fila</TableHead>
                      <TableHead>Dato</TableHead>
                      <TableHead>Error</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {resultado.errores.map((e, i) => (
                      <TableRow key={i}>
                        <TableCell className="tabular-nums">{e.fila}</TableCell>
                        <TableCell className="font-mono text-xs">{String(e.sku ?? e.concepto ?? "")}</TableCell>
                        <TableCell className="text-xs">{e.error}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}
            <DialogFooter>
              <Button variant="outline" onClick={reset}>Subir otro archivo</Button>
              <Button onClick={() => onOpenChange(false)}>Cerrar</Button>
            </DialogFooter>
          </div>
        ) : (
          <div className="space-y-4">
            {endpointPlantilla && (
              <div className="flex items-center justify-between rounded-md border p-3 text-sm">
                <span className="text-muted-foreground">1. Descarga la plantilla y llénala (o usa tu propio archivo con las mismas columnas).</span>
                <Button variant="outline" size="sm" onClick={() => apiDownload(endpointPlantilla, nombrePlantilla).catch(() => setError("No se pudo descargar la plantilla"))}>
                  <Download className="mr-2 h-4 w-4" /> Plantilla
                </Button>
              </div>
            )}
            <div className="space-y-1.5">
              <Label htmlFor="archivo-carga">{endpointPlantilla ? "2. Archivo" : "Archivo"} (.xlsx o .csv)</Label>
              <Input id="archivo-carga" ref={inputRef} type="file" accept=".xlsx,.xlsm,.csv,.txt" onChange={(e) => setArchivo(e.target.files?.[0] ?? null)} />
              <p className="text-xs text-muted-foreground">Las columnas se reconocen por nombre (sin importar mayúsculas o acentos); el encabezado puede estar en cualquiera de las primeras filas.</p>
            </div>
            {error && <p className="text-sm text-destructive">{error}</p>}
            <DialogFooter>
              <Button variant="outline" onClick={() => onOpenChange(false)}>Cancelar</Button>
              <Button onClick={importar} disabled={subiendo}>
                <FileUp className="mr-2 h-4 w-4" /> {subiendo ? "Importando…" : "Importar"}
              </Button>
            </DialogFooter>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
