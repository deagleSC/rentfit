import type { ReactNode } from "react";

import { TenantShell } from "@/components/tenant-shell";
import { TenantUserMenu } from "@/components/user-menu";

export default function AppLayout({ children }: { children: ReactNode }) {
  return (
    <TenantShell subtitle="Tenant" footer={<TenantUserMenu />}>
      {children}
    </TenantShell>
  );
}
