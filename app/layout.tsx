import type { Metadata } from "next";
import { Manrope, Space_Grotesk } from "next/font/google";

import { AppProviders } from "@/components/providers/AppProviders";
import "./globals.css";

const manrope = Manrope({
  variable: "--font-body",
  subsets: ["latin"],
  display: "swap"
});

const spaceGrotesk = Space_Grotesk({
  variable: "--font-display",
  subsets: ["latin"],
  display: "swap"
});

export const metadata: Metadata = {
  title: "KrishiMitra AgroTech Platform",
  description:
    "Advanced multilingual farmer platform with crop AI, irrigation planning, weather intelligence, marketplace, rental and scheme guidance."
};

export default function RootLayout({
  children
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className={`${manrope.variable} ${spaceGrotesk.variable}`}>
        <AppProviders>{children}</AppProviders>
      </body>
    </html>
  );
}
