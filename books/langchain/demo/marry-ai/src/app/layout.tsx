import type { Metadata } from "next";
import "./globals.css";
import { Noto_Serif_SC, Noto_Sans_SC } from "next/font/google";
import React from "react";
import { NuqsAdapter } from "nuqs/adapters/next/app";

const notoSerif = Noto_Serif_SC({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  preload: true,
  display: "swap",
  variable: "--font-serif",
});

const notoSans = Noto_Sans_SC({
  subsets: ["latin"],
  weight: ["300", "400", "500", "600"],
  preload: true,
  display: "swap",
  variable: "--font-sans",
});

export const metadata: Metadata = {
  title: "MarryAI - 智能婚礼策划助手",
  description: "AI-powered wedding planning assistant - 让您的婚礼梦想成真",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN" suppressHydrationWarning>
      <body className={`${notoSerif.variable} ${notoSans.variable} font-sans antialiased bg-wedding-pattern bg-sparkle`}>
        <NuqsAdapter>{children}</NuqsAdapter>
      </body>
    </html>
  );
}
