"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { FileUp, Plus, X } from "lucide-react";

import { CargaMasivaDialog } from "@/components/carga-masiva-dialog";
import { useEmpresa } from "@/components/empresa-provider";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ApiError, apiFetch } from "@/lib/api";
import { formatDate, formatMoney, formatUnit } from "@/lib/format";
import { PERM, can } from "@/lib/permissions";
import type { Almacen, Movimiento, Producto, StockItem } from "@/lib/types";

const TIPO_MOV_VARIANT = {
  entrada: "success",
  salida: "destructive",
  ajuste: "secondary",
} as const;

const TODAS_CATEGORIAS = "__todas__";

interface AtributoField {
  clave: string;
  valor: string;
}

export default function InventarioPage() {
  const { empresaActiva } = useEmpresa();
  const [stock, setStock] = useState<StockItem[]>([]);
  const [movimientos, setMovimientos] = useState<Movimiento[]>([]);
  const [almacenes, setAlmacenes] = useState<Almacen[]>([]);
  const [productos, setProductos] = useState<Producto[]>([]);
  const [categorias, setCategorias] = useState<string[]>([]);
  const [filtroCategoria, setFiltroCategoria] = useState(TODAS_CATEGORIAS);
  const [loading, setLoading] = useState(true);

  // --- diálogo: registrar movimiento ---
  const [openMov, setOpenMov] = useState(false);
  const [errorMov, setErrorMov] = useState<string | null>(null);
  const [submittingMov, setSubmittingMov] = useState(false);
  const [sku, setSku] = useState("");
  const [codigoAlmacen, setCodigoAlmacen] = useState("");
  const [tipoMov, setTipoMov] = useState("entrada");
  const [cantidad, setCantidad] = useState("1");
  const [nota, setNota] = useState("");

  // --- diálogo: nuevo producto ---
  const [openProd, setOpenProd] = useState(false);
  const [errorProd, setErrorProd] = useState<string | null>(null);
  const [submittingProd, setSubmittingProd] = useState(false);
  const [nuevoSku, setNuevoSku] = useState("");
  const [nuevoNombre, setNuevoNombre] = useState("");
  const [nuevoTipo, setNuevoTipo] = useState("producto");
  const [nuevaCategoria, setNuevaCategoria] = useState("");
  const [nuevoCosto, setNuevoCosto] = useState("0");
  const [atributos, setAtributos] = useState<AtributoField[]>([]);

  // --- carga masiva ---
  const [openCargaProd, setOpenCargaProd] = useState(false);
  const [openCargaMov, setOpenCargaMov] = useState(false);

  const cargar = useCallback(async () => {
    setLoading(true);
    try {
      const [s, m, a, p, c] = await Promise.all([
        apiFetch<StockItem[]>("/inventory/stock"),
        apiFetch<Movimiento[]>("/inventory/movimientos?limit=100"),
        apiFetch<Almacen[]>("/inventory/almacenes"),
        apiFetch<Producto[]>("/inventory/productos"),
        apiFetch<string[]>("/inventory/categorias"),
      ]);
      setStock(s);
      setMovimientos(m);
      setAlmacenes(a);
      setProductos(p);
      setCategorias(c);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (empresaActiva) void cargar();
  }, [empresaActiva, cargar]);

  const stockFiltrado = useMemo(() => {
    if (filtroCategoria === TODAS_CATEGORIAS) return stock;
    const skusDeCategoria = new Set(productos.filter((p) => p.categoria === filtroCategoria).map((p) => p.sku));
    return stock.filter((s) => skusDeCategoria.has(s.sku));
  }, [stock, productos, filtroCategoria]);

  function resetFormMov() {
    setSku("");
    setCodigoAlmacen("");
    setTipoMov("entrada");
    setCantidad("1");
    setNota("");
    setErrorMov(null);
  }

  async function handleSubmitMov(e: React.FormEvent) {
    e.preventDefault();
    setErrorMov(null);
    setSubmittingMov(true);
    try {
      const cantidadNum = Number(cantidad);
      const cantidadFinal = tipoMov === "salida" ? -Math.abs(cantidadNum) : Math.abs(cantidadNum);
      await apiFetch("/inventory/movimientos", {
        method: "POST",
        body: JSON.stringify({
          sku,
          codigo_almacen: codigoAlmacen,
          tipo: tipoMov,
          cantidad: tipoMov === "ajuste" ? cantidadNum : cantidadFinal,
          nota: nota || undefined,
        }),
      });
      setOpenMov(false);
      resetFormMov();
      await cargar();
    } catch (err) {
      setErrorMov(err instanceof ApiError ? err.message : "Error al registrar el movimiento");
    } finally {
      setSubmittingMov(false);
    }
  }

  function resetFormProd() {
    setNuevoSku("");
    setNuevoNombre("");
    setNuevoTipo("producto");
    setNuevaCategoria("");
    setNuevoCosto("0");
    setAtributos([]);
    setErrorProd(null);
  }

  function agregarAtributo() {
    setAtributos((prev) => [...prev, { clave: "", valor: "" }]);
  }

  function actualizarAtributo(idx: number, campo: "clave" | "valor", valor: string) {
    setAtributos((prev) => prev.map((a, i) => (i === idx ? { ...a, [campo]: valor } : a)));
  }

  function quitarAtributo(idx: number) {
    setAtributos((prev) => prev.filter((_, i) => i !== idx));
  }

  async function handleSubmitProd(e: React.FormEvent) {
    e.preventDefault();
    setErrorProd(null);
    setSubmittingProd(true);
    try {
      const atributosObj = Object.fromEntries(
        atributos.filter((a) => a.clave.trim()).map((a) => [a.clave.trim(), a.valor]),
      );
      await apiFetch("/inventory/productos", {
        method: "POST",
        body: JSON.stringify({
          sku: nuevoSku,
          nombre: nuevoNombre,
          tipo: nuevoTipo,
          categoria: nuevaCategoria || undefined,
          costo_unitario: Number(nuevoCosto),
          atributos: Object.keys(atributosObj).length > 0 ? atributosObj : undefined,
        }),
      });
      setOpenProd(false);
      resetFormProd();
      await cargar();
    } catch (err) {
      setErrorProd(err instanceof ApiError ? err.message : "Error al crear el producto");
    } finally {
      setSubmittingProd(false);
    }
  }

  if (!empresaActiva) return null;
  const puedeAjustar = can(empresaActiva.permisos, PERM.INVENTARIO_AJUSTAR);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Inventario</h1>
          <p className="text-sm text-muted-foreground">
            Catálogo adaptable: cualquier producto o servicio, con categorías y atributos propios.
          </p>
        </div>
        {puedeAjustar && (
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" onClick={() => setOpenCargaProd(true)}>
              <FileUp /> Importar productos
            </Button>
            <Button variant="outline" onClick={() => setOpenCargaMov(true)}>
              <FileUp /> Importar movimientos
            </Button>
            <CargaMasivaDialog
              open={openCargaProd}
              onOpenChange={setOpenCargaProd}
              titulo="Importar productos desde Excel"
              descripcion="Alta o actualización masiva por SKU. Columnas: SKU, Nombre, Tipo, Categoría, Unidad SAT, Costo unitario, Clave SAT, Activo; cualquier columna extra se guarda como atributo."
              endpointImportar="/inventory/productos/importar"
              endpointPlantilla="/inventory/productos/plantilla"
              nombrePlantilla="plantilla_productos.xlsx"
              etiquetaCreados="productos nuevos"
              etiquetaActualizados="actualizados"
              onImportado={() => void cargar()}
            />
            <CargaMasivaDialog
              open={openCargaMov}
              onOpenChange={setOpenCargaMov}
              titulo="Importar movimientos desde Excel"
              descripcion="Entradas, salidas y ajustes en lote. Columnas: SKU, Almacén (código), Tipo, Cantidad, Costo unitario, Referencia, Nota. Las salidas que dejen stock negativo se rechazan por fila."
              endpointImportar="/inventory/movimientos/importar"
              endpointPlantilla="/inventory/movimientos/plantilla"
              nombrePlantilla="plantilla_movimientos.xlsx"
              etiquetaCreados="movimientos registrados"
              onImportado={() => void cargar()}
            />
            <Dialog
              open={openProd}
              onOpenChange={(o) => {
                setOpenProd(o);
                if (!o) resetFormProd();
              }}
            >
              <DialogTrigger asChild>
                <Button variant="outline">
                  <Plus /> Nuevo producto
                </Button>
              </DialogTrigger>
              <DialogContent>
                <DialogHeader>
                  <DialogTitle>Nuevo producto o servicio</DialogTitle>
                </DialogHeader>
                <form onSubmit={handleSubmitProd} className="space-y-4">
                  <div className="grid grid-cols-2 gap-3">
                    <div className="space-y-2">
                      <Label>SKU</Label>
                      <Input value={nuevoSku} onChange={(e) => setNuevoSku(e.target.value)} required />
                    </div>
                    <div className="space-y-2">
                      <Label>Tipo</Label>
                      <Select value={nuevoTipo} onValueChange={setNuevoTipo}>
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="producto">Producto (con stock)</SelectItem>
                          <SelectItem value="servicio">Servicio (sin stock)</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                  </div>
                  <div className="space-y-2">
                    <Label>Nombre</Label>
                    <Input value={nuevoNombre} onChange={(e) => setNuevoNombre(e.target.value)} required />
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div className="space-y-2">
                      <Label>Categoría</Label>
                      <Input
                        value={nuevaCategoria}
                        onChange={(e) => setNuevaCategoria(e.target.value)}
                        placeholder="Ej. Cómputo"
                        list="categorias-existentes"
                      />
                      <datalist id="categorias-existentes">
                        {categorias.map((c) => (
                          <option key={c} value={c} />
                        ))}
                      </datalist>
                    </div>
                    <div className="space-y-2">
                      <Label>Costo unitario</Label>
                      <Input
                        type="number"
                        step="0.01"
                        value={nuevoCosto}
                        onChange={(e) => setNuevoCosto(e.target.value)}
                      />
                    </div>
                  </div>

                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <Label>Atributos personalizados (opcional)</Label>
                      <Button type="button" variant="ghost" size="sm" onClick={agregarAtributo}>
                        <Plus /> Agregar
                      </Button>
                    </div>
                    {atributos.map((a, idx) => (
                      <div key={idx} className="flex gap-2">
                        <Input
                          placeholder="clave (ej. color)"
                          value={a.clave}
                          onChange={(e) => actualizarAtributo(idx, "clave", e.target.value)}
                        />
                        <Input
                          placeholder="valor (ej. negro)"
                          value={a.valor}
                          onChange={(e) => actualizarAtributo(idx, "valor", e.target.value)}
                        />
                        <Button
                          type="button"
                          variant="ghost"
                          size="icon"
                          onClick={() => quitarAtributo(idx)}
                          aria-label="Quitar este atributo"
                        >
                          <X className="h-4 w-4" />
                        </Button>
                      </div>
                    ))}
                  </div>

                  {errorProd && <p className="text-sm text-destructive">{errorProd}</p>}
                  <DialogFooter>
                    <Button type="submit" disabled={submittingProd}>
                      {submittingProd ? "Guardando..." : "Guardar"}
                    </Button>
                  </DialogFooter>
                </form>
              </DialogContent>
            </Dialog>

            <Dialog
              open={openMov}
              onOpenChange={(o) => {
                setOpenMov(o);
                if (!o) resetFormMov();
              }}
            >
              <DialogTrigger asChild>
                <Button>
                  <Plus /> Registrar movimiento
                </Button>
              </DialogTrigger>
              <DialogContent>
                <DialogHeader>
                  <DialogTitle>Registrar movimiento de inventario</DialogTitle>
                </DialogHeader>
                <form onSubmit={handleSubmitMov} className="space-y-4">
                  <div className="space-y-2">
                    <Label>Producto (SKU)</Label>
                    <Select value={sku} onValueChange={setSku} required>
                      <SelectTrigger>
                        <SelectValue placeholder="Selecciona un producto" />
                      </SelectTrigger>
                      <SelectContent>
                        {productos
                          .filter((p) => p.tipo === "producto")
                          .map((p) => (
                            <SelectItem key={p.id} value={p.sku}>
                              {p.sku} — {p.nombre}
                            </SelectItem>
                          ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-2">
                    <Label>Almacén</Label>
                    <Select value={codigoAlmacen} onValueChange={setCodigoAlmacen} required>
                      <SelectTrigger>
                        <SelectValue placeholder="Selecciona un almacén" />
                      </SelectTrigger>
                      <SelectContent>
                        {almacenes.map((a) => (
                          <SelectItem key={a.id} value={a.codigo}>
                            {a.nombre}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div className="space-y-2">
                      <Label>Tipo</Label>
                      <Select value={tipoMov} onValueChange={setTipoMov}>
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="entrada">Entrada</SelectItem>
                          <SelectItem value="salida">Salida</SelectItem>
                          <SelectItem value="ajuste">Ajuste</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="space-y-2">
                      <Label>Cantidad</Label>
                      <Input
                        type="number"
                        value={cantidad}
                        onChange={(e) => setCantidad(e.target.value)}
                        required
                      />
                    </div>
                  </div>
                  <div className="space-y-2">
                    <Label>Nota (opcional)</Label>
                    <Input value={nota} onChange={(e) => setNota(e.target.value)} />
                  </div>
                  {errorMov && <p className="text-sm text-destructive">{errorMov}</p>}
                  <DialogFooter>
                    <Button type="submit" disabled={submittingMov}>
                      {submittingMov ? "Guardando..." : "Guardar"}
                    </Button>
                  </DialogFooter>
                </form>
              </DialogContent>
            </Dialog>
          </div>
        )}
      </div>

      <Tabs defaultValue="stock">
        <TabsList>
          <TabsTrigger value="stock">Stock actual</TabsTrigger>
          <TabsTrigger value="movimientos">Movimientos</TabsTrigger>
          <TabsTrigger value="productos">Productos</TabsTrigger>
        </TabsList>

        <TabsContent value="stock" className="space-y-3">
          <Select value={filtroCategoria} onValueChange={setFiltroCategoria}>
            <SelectTrigger className="w-56">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={TODAS_CATEGORIAS}>Todas las categorías</SelectItem>
              {categorias.map((c) => (
                <SelectItem key={c} value={c}>
                  {c}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          <Card>
            <CardContent className="p-0">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>SKU</TableHead>
                    <TableHead>Producto</TableHead>
                    <TableHead>Categoría</TableHead>
                    <TableHead>Almacén</TableHead>
                    <TableHead className="text-right">Disponible</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {!loading &&
                    stockFiltrado.map((s) => (
                      <TableRow key={`${s.producto_id}-${s.almacen_id}`}>
                        <TableCell className="font-mono text-xs">{s.sku}</TableCell>
                        <TableCell>{s.nombre_producto}</TableCell>
                        <TableCell className="text-muted-foreground">{s.categoria ?? "—"}</TableCell>
                        <TableCell>{s.codigo_almacen}</TableCell>
                        <TableCell className="text-right tabular-nums">
                          <Badge variant={s.disponible > 0 ? "secondary" : "destructive"}>{s.disponible}</Badge>
                        </TableCell>
                      </TableRow>
                    ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="movimientos">
          <Card>
            <CardContent className="p-0">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Fecha</TableHead>
                    <TableHead>SKU</TableHead>
                    <TableHead>Producto</TableHead>
                    <TableHead>Almacén</TableHead>
                    <TableHead>Tipo</TableHead>
                    <TableHead className="text-right">Cantidad</TableHead>
                    <TableHead className="text-right">Costo unit.</TableHead>
                    <TableHead>Referencia / nota</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {!loading &&
                    movimientos.map((m) => (
                      <TableRow key={m.id}>
                        <TableCell>{formatDate(m.fecha)}</TableCell>
                        <TableCell className="font-mono text-xs">{m.sku}</TableCell>
                        <TableCell>{m.nombre_producto}</TableCell>
                        <TableCell>{m.codigo_almacen}</TableCell>
                        <TableCell>
                          <Badge variant={TIPO_MOV_VARIANT[m.tipo]}>{m.tipo}</Badge>
                        </TableCell>
                        <TableCell className="text-right tabular-nums">{m.cantidad}</TableCell>
                        <TableCell className="text-right tabular-nums text-muted-foreground">
                          {m.costo_unitario != null ? formatUnit(m.costo_unitario, 4) : "—"}
                        </TableCell>
                        <TableCell className="text-muted-foreground">
                          {m.referencia && <span className="mr-2 font-mono text-xs">{m.referencia}</span>}
                          {m.nota ?? ""}
                        </TableCell>
                      </TableRow>
                    ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="productos">
          <Card>
            <CardContent className="p-0">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>SKU</TableHead>
                    <TableHead>Nombre</TableHead>
                    <TableHead>Tipo</TableHead>
                    <TableHead>Categoría</TableHead>
                    <TableHead>Atributos</TableHead>
                    <TableHead className="text-right">Costo</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {!loading &&
                    productos.map((p) => (
                      <TableRow key={p.id}>
                        <TableCell className="font-mono text-xs">{p.sku}</TableCell>
                        <TableCell>{p.nombre}</TableCell>
                        <TableCell>
                          <Badge variant={p.tipo === "servicio" ? "secondary" : "outline"}>{p.tipo}</Badge>
                        </TableCell>
                        <TableCell className="text-muted-foreground">{p.categoria ?? "—"}</TableCell>
                        <TableCell>
                          <div className="flex flex-wrap gap-1">
                            {p.atributos &&
                              Object.entries(p.atributos).map(([k, v]) => (
                                <Badge key={k} variant="outline" className="font-normal">
                                  {k}: {String(v)}
                                </Badge>
                              ))}
                          </div>
                        </TableCell>
                        <TableCell className="text-right tabular-nums">{formatMoney(p.costo_unitario)}</TableCell>
                      </TableRow>
                    ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
