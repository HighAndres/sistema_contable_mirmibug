import type { Metadata } from "next";

import { AuthProvider } from "@/components/auth-provider";
import { EmpresaProvider } from "@/components/empresa-provider";
import { THEME_INIT_SCRIPT } from "@/lib/theme";

import "./globals.css";

export const metadata: Metadata = {
  title: "Nubinox — Sistema contable y de inventarios",
  description: "Bóveda fiscal, validaciones tipo EFOS, inteligencia financiera e inventarios multi-empresa.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es" suppressHydrationWarning>
      <head>
        {/* Aplica el tema guardado antes de pintar, para no parpadear en claro. */}
        <script dangerouslySetInnerHTML={{ __html: THEME_INIT_SCRIPT }} />
      </head>
      <body className="min-h-dvh antialiased">
        <AuthProvider>
          <EmpresaProvider>{children}</EmpresaProvider>
        </AuthProvider>
      </body>
    </html>
  );
}
