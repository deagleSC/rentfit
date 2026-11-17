import { AuthLayout } from "@rentfit/ui/blocks/auth-layout";
import type { ReactNode } from "react";

export default function Layout({ children }: { children: ReactNode }) {
  return <AuthLayout tagline="Describe your flat in a message. RentFit turns it into a listing you can check and publish.">{children}</AuthLayout>;
}
