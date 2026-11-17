import { AuthLayout } from "@rentfit/ui/blocks/auth-layout";
import type { ReactNode } from "react";

export default function Layout({ children }: { children: ReactNode }) {
  return <AuthLayout tagline="Say what you want in your own words. See homes that fit, with every price and distance checked.">{children}</AuthLayout>;
}
