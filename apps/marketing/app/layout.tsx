import "./globals.css";

import { UiProvider } from "@rentfit/ui/blocks/theme-provider";
import type { Metadata } from "next";
import { Inter } from "next/font/google";
import type { ReactNode } from "react";

import { SiteFooter, SiteHeader } from "@/components/site";

const fontSans = Inter({ subsets: ["latin"], variable: "--font-sans" });

export const metadata: Metadata = {
  title: { default: "RentFit: find a rental by describing it", template: "%s · RentFit" },
  description:
    "Search rentals in Bengaluru and Mumbai by chat, in English or Hinglish. Landlords list a flat by describing it.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className={fontSans.variable} suppressHydrationWarning>
      <body className="flex min-h-svh flex-col">
        <UiProvider>
          <SiteHeader />
          <main className="flex-1">{children}</main>
          <SiteFooter />
        </UiProvider>
      </body>
    </html>
  );
}
