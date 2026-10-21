import type { Metadata, Viewport } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "ANYQ · АНЫҚ — стройка: объекты, снабжение, сметы",
  description:
    "Платформа строительства в Казахстане: объекты, снабжение, сметы, поставщики и исполнители.",
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
