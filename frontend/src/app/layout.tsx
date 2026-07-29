import type { Metadata } from "next";

import { AuthProvider } from "@/components/auth-provider";
import { EmpresaProvider } from "@/components/empresa-provider";

import "./globals.css";

export const metadata: Metadata = {
  title: "Nubinox — Sistema contable y de inventarios",
  description: "Bóveda fiscal, validaciones tipo EFOS, inteligencia financiera e inventarios multi-empresa.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es">
      <body className="min-h-dvh antialiased">
        <AuthProvider>
          <EmpresaProvider>{children}</EmpresaProvider>
        </AuthProvider>
      </body>
    </html>
  );
}
