import type { Metadata, Viewport } from "next";
import { Analytics } from "@vercel/analytics/next";

import { getSiteUrl } from "@/lib/site";

import "./globals.css";

const siteTitle = "AI 台股分析｜技術面、基本面、消息面與每日選股";
const siteDescription =
  "免費台股量化分析平台，整合真實行情、技術面、基本面估值、近期消息、每日 AI 選股、持股建議與歷史回測。";

export const metadata: Metadata = {
  metadataBase: getSiteUrl(),
  title: siteTitle,
  description: siteDescription,
  applicationName: "AI 台股分析",
  keywords: [
    "台股分析",
    "AI 選股",
    "股票技術分析",
    "台股回測",
    "台股基本面",
    "台股新聞",
    "每日選股",
    "台灣股票",
    "量化分析",
  ],
  alternates: {
    canonical: "/",
  },
  openGraph: {
    type: "website",
    locale: "zh_TW",
    url: "/",
    title: siteTitle,
    description: siteDescription,
    siteName: "AI 台股分析",
  },
  twitter: {
    card: "summary",
    title: siteTitle,
    description: siteDescription,
  },
  robots: {
    index: true,
    follow: true,
    googleBot: {
      index: true,
      follow: true,
      "max-image-preview": "large",
      "max-snippet": -1,
    },
  },
  category: "finance",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-Hant">
      <body>
        {children}
        <Analytics />
      </body>
    </html>
  );
}
