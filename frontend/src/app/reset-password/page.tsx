"use client";

import { Suspense, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";

import * as auth from "@/lib/auth-client";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

function ResetPasswordForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const token = searchParams.get("token") ?? "";

  const [newPassword, setNewPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [ok, setOk] = useState(false);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await auth.resetPassword(token, newPassword);
      setOk(true);
      setTimeout(() => router.replace("/login"), 2000);
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo restablecer la contraseña");
    } finally {
      setLoading(false);
    }
  }

  return (
    <Card className="w-full max-w-sm">
      <CardHeader>
        <CardTitle className="text-2xl text-primary">Nueva contraseña</CardTitle>
        <CardDescription>Define tu nueva contraseña de acceso.</CardDescription>
      </CardHeader>
      <CardContent>
        {ok ? (
          <p className="text-sm">Contraseña actualizada. Redirigiendo al login...</p>
        ) : !token ? (
          <p className="text-sm text-destructive">Enlace inválido: falta el token.</p>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="new_password">Nueva contraseña</Label>
              <Input
                id="new_password"
                type="password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                required
                minLength={8}
              />
            </div>
            {error && <p className="text-sm text-destructive">{error}</p>}
            <Button type="submit" className="w-full" disabled={loading}>
              {loading ? "Guardando..." : "Restablecer contraseña"}
            </Button>
          </form>
        )}
        <p className="mt-4 text-xs text-muted-foreground">
          <Link href="/login" className="underline">
            Volver a iniciar sesión
          </Link>
        </p>
      </CardContent>
    </Card>
  );
}

export default function ResetPasswordPage() {
  return (
    <div className="flex min-h-dvh items-center justify-center bg-muted/40 p-4">
      <Suspense fallback={null}>
        <ResetPasswordForm />
      </Suspense>
    </div>
  );
}
