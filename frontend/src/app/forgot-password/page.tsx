"use client";

import { useState } from "react";
import Link from "next/link";

import * as auth from "@/lib/auth-client";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [mensaje, setMensaje] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    try {
      setMensaje(await auth.forgotPassword(email));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-dvh items-center justify-center bg-muted/40 p-4">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle className="text-2xl text-primary">Recuperar contraseña</CardTitle>
          <CardDescription>Te diremos si el correo existe y qué sigue.</CardDescription>
        </CardHeader>
        <CardContent>
          {mensaje ? (
            <p className="text-sm">{mensaje}</p>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="email">Correo</Label>
                <Input id="email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
              </div>
              <Button type="submit" className="w-full" disabled={loading}>
                {loading ? "Enviando..." : "Enviar instrucciones"}
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
    </div>
  );
}
