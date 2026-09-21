import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "ANYQ · АНЫҚ — ясность земли Алматы",
  description: "Сначала ясность, потом лопата. Каталог участков, паспорт риска, действие.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ru">
      <body className="font-sans">{children}</body>
    </html>
  );
}
