import "./globals.css";

import { UiProvider } from "@rentfit/ui/blocks/theme-provider";
import type { Metadata } from "next";
import { Outfit } from "next/font/google";
import type { ReactNode } from "react";

import { Providers } from "./providers";

const fontSans = Outfit({ subsets: ["latin"], variable: "--font-sans" });

export const metadata: Metadata = {
  title: { default: "RentFit for landlords", template: "%s · RentFit" },
  description: "List your flat by describing it in chat.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className={fontSans.variable} suppressHydrationWarning>
      <body>
        <UiProvider>
          <Providers>{children}</Providers>
        </UiProvider>
      </body>
    </html>
  );
}
