import type { Metadata } from "next";
import { Plus_Jakarta_Sans } from "next/font/google";
import "./globals.css";

const font = Plus_Jakarta_Sans({
  subsets: ["latin"],
  variable: "--font-sans",
});

export const metadata: Metadata = {
  title: "Loopfy — Live Commerce Automation",
  description:
    "Sua operação de lives em movimento: produtos, comentários, moderação e alertas de venda em um só painel.",
  icons: { icon: "/loopfy-icon.png" },
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="pt-BR" className={font.variable}>
      <body className="antialiased">{children}</body>
    </html>
  );
}
