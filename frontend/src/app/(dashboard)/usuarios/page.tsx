"use client";

import { useCallback, useEffect, useState } from "react";
import { Plus, Shield, Trash2 } from "lucide-react";

import { useAuth } from "@/components/auth-provider";
import { useEmpresa } from "@/components/empresa-provider";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ApiError, apiFetch } from "@/lib/api";
import { PERM, can } from "@/lib/permissions";
import type { InvitarUsuarioResponse, MiembroEmpresa, UsuarioAdmin } from "@/lib/types";

function SeccionMiembrosEmpresa() {
  const { empresaActiva } = useEmpresa();
  const [miembros, setMiembros] = useState<MiembroEmpresa[]>([]);
  const [loading, setLoading] = useState(true);

  const [open, setOpen] = useState(false);
  const [email, setEmail] = useState("");
  const [nombreCompleto, setNombreCompleto] = useState("");
  const [rolNombre, setRolNombre] = useState("contador");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [resultado, setResultado] = useState<InvitarUsuarioResponse | null>(null);

  const cargar = useCallback(async () => {
    setLoading(true);
    try {
      setMiembros(await apiFetch<MiembroEmpresa[]>("/tenants/usuarios"));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (empresaActiva) void cargar();
  }, [empresaActiva, cargar]);

  function resetForm() {
    setEmail("");
    setNombreCompleto("");
    setRolNombre("contador");
    setError(null);
    setResultado(null);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const r = await apiFetch<InvitarUsuarioResponse>("/tenants/usuarios/invitar", {
        method: "POST",
        body: JSON.stringify({ email, nombre_completo: nombreCompleto || undefined, rol_nombre: rolNombre }),
      });
      setResultado(r);
      await cargar();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "No se pudo invitar al usuario");
    } finally {
      setSubmitting(false);
    }
  }

  if (!empresaActiva) return null;
  const puedeInvitar = can(empresaActiva.permisos, PERM.USUARIOS_INVITAR);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Usuarios</h1>
          <p className="text-sm text-muted-foreground">Miembros de {empresaActiva.empresa.razon_social}</p>
        </div>
        {puedeInvitar && (
          <Dialog
            open={open}
            onOpenChange={(o) => {
              setOpen(o);
              if (!o) resetForm();
            }}
          >
            <DialogTrigger asChild>
              <Button>
                <Plus /> Invitar usuario
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Invitar usuario a la empresa</DialogTitle>
              </DialogHeader>

              {resultado ? (
                <div className="space-y-3 text-sm">
                  <p>
                    <strong>{resultado.email}</strong> agregado como <strong>{resultado.rol}</strong>.
                  </p>
                  {resultado.password_temporal && (
                    <div className="rounded-md border bg-muted p-3">
                      <p className="text-muted-foreground">
                        Cuenta nueva creada. Comparte esta contraseña temporal (no se enviará por correo):
                      </p>
                      <p className="mt-1 font-mono text-sm">{resultado.password_temporal}</p>
                    </div>
                  )}
                  <DialogFooter>
                    <Button
                      onClick={() => {
                        setOpen(false);
                        resetForm();
                      }}
                    >
                      Cerrar
                    </Button>
                  </DialogFooter>
                </div>
              ) : (
                <form onSubmit={handleSubmit} className="space-y-4">
                  <div className="space-y-2">
                    <Label>Correo</Label>
                    <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
                  </div>
                  <div className="space-y-2">
                    <Label>Nombre</Label>
                    <Input value={nombreCompleto} onChange={(e) => setNombreCompleto(e.target.value)} />
                  </div>
                  <div className="space-y-2">
                    <Label>Rol en la empresa</Label>
                    <Select value={rolNombre} onValueChange={setRolNombre}>
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="administrador">Administrador</SelectItem>
                        <SelectItem value="contador">Contador</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  {error && <p className="text-sm text-destructive">{error}</p>}
                  <p className="text-xs text-muted-foreground">
                    Solo se pueden invitar correos que no tengan cuenta todavía (se crea una nueva). Vincular una
                    cuenta ya existente a esta empresa requiere un superadmin.
                  </p>
                  <DialogFooter>
                    <Button type="submit" disabled={submitting}>
                      {submitting ? "Invitando..." : "Invitar"}
                    </Button>
                  </DialogFooter>
                </form>
              )}
            </DialogContent>
          </Dialog>
        )}
      </div>

      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Nombre</TableHead>
                <TableHead>Correo</TableHead>
                <TableHead>Rol</TableHead>
                <TableHead>Estado</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {!loading &&
                miembros.map((m) => (
                  <TableRow key={m.usuario_id}>
                    <TableCell>{m.nombre_completo ?? "—"}</TableCell>
                    <TableCell className="text-muted-foreground">{m.email}</TableCell>
                    <TableCell>
                      <Badge variant="secondary">{m.rol}</Badge>
                    </TableCell>
                    <TableCell>
                      <Badge variant={m.is_active ? "success" : "destructive"}>
                        {m.is_active ? "activo" : "inactivo"}
                      </Badge>
                    </TableCell>
                  </TableRow>
                ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}

function SeccionSuperadmin() {
  const { user } = useAuth();
  const [usuarios, setUsuarios] = useState<UsuarioAdmin[]>([]);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);
  const [email, setEmail] = useState("");
  const [nombreCompleto, setNombreCompleto] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const cargar = useCallback(async () => {
    setLoading(true);
    try {
      setUsuarios(await apiFetch<UsuarioAdmin[]>("/admin/usuarios"));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void cargar();
  }, [cargar]);

  async function crear(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await apiFetch("/admin/usuarios", {
        method: "POST",
        body: JSON.stringify({ email, password, nombre_completo: nombreCompleto || undefined }),
      });
      setOpen(false);
      setEmail("");
      setNombreCompleto("");
      setPassword("");
      await cargar();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "No se pudo crear el usuario");
    } finally {
      setSubmitting(false);
    }
  }

  async function toggleActivo(u: UsuarioAdmin) {
    await apiFetch(`/admin/usuarios/${u.id}/${u.is_active ? "desactivar" : "activar"}`, { method: "POST" });
    await cargar();
  }

  async function eliminar(u: UsuarioAdmin) {
    if (!confirm(`¿Eliminar la cuenta de ${u.email}? Esta acción no se puede deshacer.`)) return;
    await apiFetch(`/admin/usuarios/${u.id}`, { method: "DELETE" });
    await cargar();
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0">
        <div className="flex items-center gap-2">
          <Shield className="h-5 w-5 text-primary" />
          <CardTitle className="text-base">Administración de la plataforma (superadmin)</CardTitle>
        </div>
        <Dialog open={open} onOpenChange={setOpen}>
          <DialogTrigger asChild>
            <Button variant="outline" size="sm">
              <Plus /> Crear usuario
            </Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Crear usuario del sistema</DialogTitle>
            </DialogHeader>
            <form onSubmit={crear} className="space-y-4">
              <div className="space-y-2">
                <Label>Correo</Label>
                <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
              </div>
              <div className="space-y-2">
                <Label>Nombre</Label>
                <Input value={nombreCompleto} onChange={(e) => setNombreCompleto(e.target.value)} />
              </div>
              <div className="space-y-2">
                <Label>Contraseña</Label>
                <Input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  minLength={8}
                  required
                />
              </div>
              {error && <p className="text-sm text-destructive">{error}</p>}
              <DialogFooter>
                <Button type="submit" disabled={submitting}>
                  {submitting ? "Creando..." : "Crear"}
                </Button>
              </DialogFooter>
            </form>
          </DialogContent>
        </Dialog>
      </CardHeader>
      <CardContent className="p-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Correo</TableHead>
              <TableHead>Nombre</TableHead>
              <TableHead>Empresas</TableHead>
              <TableHead>Estado</TableHead>
              <TableHead className="text-right">Acciones</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {!loading &&
              usuarios.map((u) => (
                <TableRow key={u.id}>
                  <TableCell className="text-muted-foreground">{u.email}</TableCell>
                  <TableCell>{u.nombre_completo ?? "—"}</TableCell>
                  <TableCell>{u.is_superadmin ? "todas" : u.num_empresas}</TableCell>
                  <TableCell>
                    <Badge variant={u.is_active ? "success" : "destructive"}>
                      {u.is_active ? "activo" : "inactivo"}
                    </Badge>
                  </TableCell>
                  <TableCell className="flex justify-end gap-2">
                    {u.id !== user?.id && (
                      <>
                        <Button variant="outline" size="sm" onClick={() => toggleActivo(u)}>
                          {u.is_active ? "Desactivar" : "Activar"}
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={() => eliminar(u)}
                          aria-label={`Eliminar a ${u.email}`}
                        >
                          <Trash2 className="h-4 w-4 text-destructive" />
                        </Button>
                      </>
                    )}
                  </TableCell>
                </TableRow>
              ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}

export default function UsuariosPage() {
  const { user } = useAuth();
  return (
    <div className="space-y-8">
      <SeccionMiembrosEmpresa />
      {user?.is_superadmin && <SeccionSuperadmin />}
    </div>
  );
}
