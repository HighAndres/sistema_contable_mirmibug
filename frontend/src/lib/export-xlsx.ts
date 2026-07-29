import * as XLSX from "xlsx";

/** Exporta una o más hojas a un .xlsx y dispara la descarga en el navegador. */
export function exportarExcel(nombreArchivo: string, hojas: Record<string, Record<string, unknown>[]>): void {
  const libro = XLSX.utils.book_new();
  for (const [nombreHoja, filas] of Object.entries(hojas)) {
    const hoja = XLSX.utils.json_to_sheet(filas);
    XLSX.utils.book_append_sheet(libro, hoja, nombreHoja.slice(0, 31));
  }
  XLSX.writeFile(libro, `${nombreArchivo}.xlsx`);
}
