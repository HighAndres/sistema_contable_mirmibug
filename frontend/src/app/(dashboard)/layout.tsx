"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import {
  Banknote,
  Building2,
  Calculator,
  Contact,
  Truck,
  ClipboardList,
  LayoutDashboard,
  LogOut,
  Menu,
  Package,
  Percent,
  Scale,
  Receipt,
  Ship,
  Users,
} from "lucide-react";

import { useAuth } from "@/components/auth-provider";
import { useEmpresa } from "@/components/empresa-provider";
import { ThemeToggle } from "@/components/theme-toggle";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { Separator } from "@/components/ui/separator";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { PERM, type Permiso, canAny } from "@/lib/permissions";
import { cn } from "@/lib/utils";
import type { MiEmpresa, Usuario } from "@/lib/types";

interface NavItem {
  href: string;
  label: string;
  icon: React.ElementType;
  permisos: Permiso[];
}

/** La navegación va por grupos: con 13 entradas planas ya no se distinguía lo
 * fiscal de lo operativo ni de la administración. El grupo se oculta completo
 * cuando el usuario no tiene permiso para ninguna de sus entradas. */
interface NavGrupo {
  titulo: string;
  items: NavItem[];
}

const NAV_GRUPOS: NavGrupo[] = [
  {
    titulo: "General",
    items: [
      { href: "/", label: "Dashboard", icon: LayoutDashboard, permisos: [] },
      { href: "/reportes", label: "Reportes", icon: Banknote, permisos: [PERM.REPORTES_LEER] },
    ],
  },
  {
    titulo: "Fiscal",
    items: [
      { href: "/cfdi", label: "CFDI", icon: Receipt, permisos: [PERM.CFDI_LEER] },
      { href: "/iva", label: "IVA", icon: Percent, permisos: [PERM.IMPUESTOS_LEER] },
      { href: "/isr", label: "ISR", icon: Calculator, permisos: [PERM.IMPUESTOS_LEER] },
      { href: "/conciliacion", label: "Conciliación", icon: Scale, permisos: [PERM.CONCILIACION_LEER] },
    ],
  },
  {
    titulo: "Operación",
    items: [
      { href: "/inventario", label: "Inventario", icon: Package, permisos: [PERM.INVENTARIO_LEER] },
      { href: "/pedimentos", label: "Pedimentos", icon: Ship, permisos: [PERM.PEDIMENTOS_LEER] },
      { href: "/clientes", label: "Clientes", icon: Contact, permisos: [PERM.TERCEROS_LEER] },
      { href: "/proveedores", label: "Proveedores", icon: Truck, permisos: [PERM.TERCEROS_LEER] },
    ],
  },
  {
    titulo: "Administración",
    items: [
      { href: "/empresas", label: "Empresas", icon: Building2, permisos: [] },
      { href: "/usuarios", label: "Usuarios", icon: Users, permisos: [PERM.USUARIOS_LEER] },
      { href: "/bitacora", label: "Bitácora", icon: ClipboardList, permisos: [PERM.BITACORA_LEER] },
    ],
  },
];

interface SidebarContentProps {
  grupos: NavGrupo[];
  pathname: string;
  user: Usuario;
  empresaActiva: MiEmpresa | null;
  onNavigate?: () => void;
  onLogout: () => void;
}

function SidebarContent({ grupos, pathname, user, empresaActiva, onNavigate, onLogout }: SidebarContentProps) {
  return (
    <div className="flex h-full flex-col">
      <div className="flex h-14 items-center px-4 text-lg font-semibold text-primary">Nubinox</div>
      <Separator />
      <nav className="flex-1 space-y-4 overflow-y-auto p-3">
        {grupos.map((grupo) => (
          <div key={grupo.titulo} className="space-y-1">
            <p className="px-3 pb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground/70">{grupo.titulo}</p>
            {grupo.items.map((item) => {
              const activo = pathname === item.href;
              const Icon = item.icon;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  onClick={onNavigate}
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
          </div>
        ))}
      </nav>
      <Separator />
      <div className="space-y-3 p-3">
        <Link href="/perfil" onClick={onNavigate} className="flex items-center gap-2 rounded-md p-1 hover:bg-accent">
          <Avatar>
            <AvatarFallback>{(user.nombre_completo ?? user.email).slice(0, 1).toUpperCase()}</AvatarFallback>
          </Avatar>
          <div className="min-w-0">
            <p className="truncate text-sm font-medium">{user.nombre_completo ?? user.email}</p>
            <p className="truncate text-xs text-muted-foreground">{empresaActiva?.rol ?? ""}</p>
          </div>
        </Link>
        <button
          onClick={onLogout}
          className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-sm text-muted-foreground hover:bg-accent hover:text-accent-foreground"
        >
          <LogOut className="h-4 w-4" />
          Cerrar sesión
        </button>
      </div>
    </div>
  );
}

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const { user, loading: authLoading, logout } = useAuth();
  const { empresas, empresaActiva, loading: empresasLoading, seleccionarEmpresa } = useEmpresa();
  const router = useRouter();
  const pathname = usePathname();
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

  useEffect(() => {
    if (authLoading) return;
    if (!user) router.replace("/login");
  }, [authLoading, user, router]);

  useEffect(() => {
    setMobileNavOpen(false);
  }, [pathname]);

  if (authLoading || !user) return null;

  const permisos = empresaActiva?.permisos ?? [];
  const visibleGrupos = NAV_GRUPOS.map((g) => ({ ...g, items: g.items.filter((item) => canAny(permisos, item.permisos)) })).filter((g) => g.items.length > 0);

  function handleLogout() {
    logout();
    router.replace("/login");
  }

  return (
    <div className="flex min-h-dvh">
      <aside className="hidden w-60 shrink-0 border-r bg-card lg:block">
        <SidebarContent grupos={visibleGrupos} pathname={pathname} user={user} empresaActiva={empresaActiva} onLogout={handleLogout} />
      </aside>

      <Dialog open={mobileNavOpen} onOpenChange={setMobileNavOpen}>
        <DialogContent className="left-0 top-0 h-dvh w-72 max-w-[85vw] translate-x-0 translate-y-0 rounded-none border-r p-0 data-[state=open]:slide-in-from-left data-[state=closed]:slide-out-to-left">
          <DialogTitle className="sr-only">Menú de navegación</DialogTitle>
          <SidebarContent
            grupos={visibleGrupos}
            pathname={pathname}
            user={user}
            empresaActiva={empresaActiva}
            onNavigate={() => setMobileNavOpen(false)}
            onLogout={handleLogout}
          />
        </DialogContent>
      </Dialog>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 items-center gap-3 border-b bg-card px-4">
          <button
            aria-label="Abrir menú de navegación"
            onClick={() => setMobileNavOpen(true)}
            className="rounded-md p-2 text-muted-foreground hover:bg-accent hover:text-accent-foreground lg:hidden"
          >
            <Menu className="h-5 w-5" />
          </button>
          <span className="text-lg font-semibold text-primary lg:hidden">Nubinox</span>
          <div className="flex-1" />
          {!empresasLoading && empresas.length > 0 && (
            <Select value={empresaActiva?.empresa.id} onValueChange={seleccionarEmpresa}>
              <SelectTrigger className="w-40 sm:w-64">
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
          <ThemeToggle />
        </header>
        <main className="min-w-0 flex-1 overflow-y-auto bg-background p-4 sm:p-6 lg:p-8">
          {!empresasLoading && empresas.length === 0 && pathname !== "/empresas" ? (
            <div className="mx-auto max-w-md rounded-lg border bg-card p-6 text-center">
              <p className="mb-4 text-sm text-muted-foreground">Aún no perteneces a ninguna empresa. Crea la primera para empezar.</p>
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
