"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import {
  Banknote,
  Building2,
  ClipboardList,
  LayoutDashboard,
  LogOut,
  Package,
  Receipt,
  Users,
} from "lucide-react";

import { useAuth } from "@/components/auth-provider";
import { useEmpresa } from "@/components/empresa-provider";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Separator } from "@/components/ui/separator";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { PERM, type Permiso, canAny } from "@/lib/permissions";
import { cn } from "@/lib/utils";

interface NavItem {
  href: string;
  label: string;
  icon: React.ElementType;
  permisos: Permiso[];
}

const NAV_ITEMS: NavItem[] = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard, permisos: [] },
  { href: "/cfdi", label: "CFDI", icon: Receipt, permisos: [PERM.CFDI_LEER] },
  { href: "/inventario", label: "Inventario", icon: Package, permisos: [PERM.INVENTARIO_LEER] },
  { href: "/reportes", label: "Reportes", icon: Banknote, permisos: [PERM.REPORTES_LEER] },
  { href: "/bitacora", label: "Bitácora", icon: ClipboardList, permisos: [PERM.BITACORA_LEER] },
  { href: "/usuarios", label: "Usuarios", icon: Users, permisos: [PERM.USUARIOS_LEER] },
  { href: "/empresas", label: "Empresas", icon: Building2, permisos: [] },
];

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const { user, loading: authLoading, logout } = useAuth();
  const { empresas, empresaActiva, loading: empresasLoading, seleccionarEmpresa } = useEmpresa();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (authLoading) return;
    if (!user) router.replace("/login");
  }, [authLoading, user, router]);

  if (authLoading || !user) return null;

  const permisos = empresaActiva?.permisos ?? [];
  const visibleItems = NAV_ITEMS.filter((item) => canAny(permisos, item.permisos));

  return (
    <div className="flex min-h-dvh">
      <aside className="hidden w-60 shrink-0 flex-col border-r bg-card lg:flex">
        <div className="flex h-14 items-center px-4 text-lg font-semibold text-primary">
          Nubinox
        </div>
        <Separator />
        <nav className="flex-1 space-y-1 p-3">
          {visibleItems.map((item) => {
            const activo = pathname === item.href;
            const Icon = item.icon;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                  activo ? "bg-accent text-accent-foreground" : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
                )}
              >
                <Icon className="h-4 w-4" />
                {item.label}
              </Link>
            );
          })}
        </nav>
        <Separator />
        <div className="space-y-3 p-3">
          <Link href="/perfil" className="flex items-center gap-2 rounded-md p-1 hover:bg-accent">
            <Avatar>
              <AvatarFallback>{(user.nombre_completo ?? user.email).slice(0, 1).toUpperCase()}</AvatarFallback>
            </Avatar>
            <div className="min-w-0">
              <p className="truncate text-sm font-medium">{user.nombre_completo ?? user.email}</p>
              <p className="truncate text-xs text-muted-foreground">{empresaActiva?.rol ?? ""}</p>
            </div>
          </Link>
          <button
            onClick={() => {
              logout();
              router.replace("/login");
            }}
            className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-sm text-muted-foreground hover:bg-accent hover:text-accent-foreground"
          >
            <LogOut className="h-4 w-4" />
            Cerrar sesión
          </button>
        </div>
      </aside>

      <div className="flex flex-1 flex-col">
        <header className="flex h-14 items-center gap-4 border-b bg-card px-4">
          <span className="text-lg font-semibold text-primary lg:hidden">Nubinox</span>
          <div className="flex-1" />
          {!empresasLoading && empresas.length > 0 && (
            <Select value={empresaActiva?.empresa.id} onValueChange={seleccionarEmpresa}>
              <SelectTrigger className="w-64">
                <SelectValue placeholder="Selecciona una empresa" />
              </SelectTrigger>
              <SelectContent>
                {empresas.map((m) => (
                  <SelectItem key={m.empresa.id} value={m.empresa.id}>
                    {m.empresa.razon_social} ({m.rol})
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
        </header>
        <main className="flex-1 overflow-y-auto bg-background p-4 sm:p-6 lg:p-8">
          {!empresasLoading && empresas.length === 0 && pathname !== "/empresas" ? (
            <div className="mx-auto max-w-md rounded-lg border bg-card p-6 text-center">
              <p className="mb-4 text-sm text-muted-foreground">
                Aún no perteneces a ninguna empresa. Crea la primera para empezar.
              </p>
              <Link href="/empresas" className="text-sm font-medium text-primary underline">
                Ir a Empresas
              </Link>
            </div>
          ) : (
            children
          )}
        </main>
      </div>
    </div>
  );
}
