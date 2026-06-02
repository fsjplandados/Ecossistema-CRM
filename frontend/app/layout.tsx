import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Eco CRM — Farmácias São João",
  description: "Dashboard de Faturamento e CRM — Farmácias São João",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="pt-BR">
      <body>{children}</body>
    </html>
  );
}
