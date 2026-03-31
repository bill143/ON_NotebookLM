import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });

export const metadata: Metadata = {
  title: "Nexus Notebook 11 LM",
  description: "AI-powered research and learning platform — Codename: ESPERANTO",
  keywords: ["notebook", "AI", "research", "learning", "LLM"],
  manifest: "/manifest.json",
  themeColor: "#6366F1",
  appleWebApp: {
    capable: true,
    statusBarStyle: "black-translucent",
    title: "Nexus LM",
  },
  viewport: {
    width: "device-width",
    initialScale: 1,
    maximumScale: 5,
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className={`${inter.variable} antialiased`}>{children}</body>
    </html>
  );
}
