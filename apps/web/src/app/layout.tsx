import type { Metadata, Viewport } from "next";
import { NativeShell } from "@/components/shell/NativeShell";
import "./globals.css";

export const metadata: Metadata = {
  title: "ANYQ · АНЫҚ — Премиальная цифровая экосистема девелопмента и строительства",
  description:
    "Безупречная точность в каждом метре и решении: аккредитованные генподрядчики, прямые поставки стройматериалов, автосмета и цифровой контроль стройплощадки в Казахстане.",
  applicationName: "Анык",
  manifest: "/manifest.webmanifest",
  appleWebApp: { capable: true, title: "Анык", statusBarStyle: "default" },
  formatDetection: { telephone: false },
  icons: {
    icon: [
      { url: "/icons/icon-192.png", sizes: "192x192", type: "image/png" },
      { url: "/icons/icon-512.png", sizes: "512x512", type: "image/png" },
    ],
    apple: [{ url: "/icons/apple-touch-icon.png", sizes: "180x180" }],
  },
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
      <body className="font-sans">
        <NativeShell />
        {children}
      </body>
    </html>
  );
}
