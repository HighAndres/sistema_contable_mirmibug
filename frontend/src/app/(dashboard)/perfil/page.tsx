"use client";

import { useState } from "react";

import { useAuth } from "@/components/auth-provider";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError, apiFetch } from "@/lib/api";

export default function PerfilPage() {
  const { user } = useAuth();
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [ok, setOk] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  if (!user) return null;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setOk(false);
    setSubmitting(true);
    try {
      await apiFetch("/auth/change-password", {
        method: "POST",
        body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
      });
      setOk(true);
      setCurrentPassword("");
      setNewPassword("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "No se pudo cambiar la contraseña");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="max-w-md space-y-4">
      <h1 className="text-2xl font-semibold">Mi perfil</h1>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Datos de la cuenta</CardTitle>
        </CardHeader>
        <CardContent className="space-y-1 text-sm">
          <p>
            <span className="text-muted-foreground">Nombre: </span>
            {user.nombre_completo ?? "—"}
          </p>
          <p>
            <span className="text-muted-foreground">Correo: </span>
            {user.email}
          </p>
          {user.is_superadmin && (
            <p className="text-muted-foreground">Cuenta de superadmin (acceso a todas las empresas).</p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Cambiar contraseña</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="current">Contraseña actual</Label>
              <Input
                id="current"
                type="password"
                value={currentPassword}
                onChange={(e) => setCurrentPassword(e.target.value)}
                required
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="new">Contraseña nueva</Label>
              <Input
                id="new"
                type="password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                required
                minLength={8}
              />
            </div>
            {error && <p className="text-sm text-destructive">{error}</p>}
            {ok && <p className="text-sm text-[color:var(--status-good)]">Contraseña actualizada.</p>}
            <Button type="submit" disabled={submitting}>
              {submitting ? "Guardando..." : "Cambiar contraseña"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
