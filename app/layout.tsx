import type { Metadata } from "next";

import { AppProviders } from "@/components/providers/AppProviders";
import "./globals.css";

/**
 * One font family for the whole app: Noto Sans + Noto Sans Devanagari share
 * metrics and weights, so Hindi and English render as one typeface instead of
 * Devanagari falling back to a mismatched system font.
 */
const FONT_STYLESHEET =
  "https://fonts.googleapis.com/css2?family=Noto+Sans:wght@400;600;700&family=Noto+Sans+Devanagari:wght@400;600;700&display=swap";

export const metadata: Metadata = {
  title: "KrishiMitra — Kisan ka Digital Saathi",
  description:
    "Find the best crop for your soil, know when to water, get the right fertilizer dose, check mandi prices and government schemes. In 11 Indian languages."
};

export default function RootLayout({
  children
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link rel="stylesheet" href={FONT_STYLESHEET} precedence="default" />
        <AppProviders>{children}</AppProviders>
      </body>
    </html>
  );
}
