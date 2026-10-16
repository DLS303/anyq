import type { Metadata, Viewport } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "ANYQ · АНЫҚ — Премиальная цифровая экосистема девелопмента и строительства",
  description:
    "Безупречная точность в каждом метре и решении: аккредитованные генподрядчики, прямые поставки стройматериалов, автосмета и цифровой контроль стройплощадки в Казахстане.",
  appleWebApp: { capable: true, title: "ANYQ", statusBarStyle: "default" },
  formatDetection: { telephone: false },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 5,
  viewportFit: "cover",
  themeColor: "#0F2942",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ru">
      <body className="font-sans">{children}</body>
    </html>
  );
}
