"use client";

import { DashboardLayout } from "@rentfit/ui/blocks/dashboard-layout";
import type { NavItem } from "@rentfit/ui/blocks/nav-main";
import { NavUser } from "@rentfit/ui/blocks/nav-user";
import { useQueryClient } from "@tanstack/react-query";
import { Building2 } from "lucide-react";
import { useRouter } from "next/navigation";
import type { ReactNode } from "react";

import { useMe } from "@/lib/api";
import { supabase } from "@/lib/supabase";

const nav: NavItem[] = [{ title: "Listings", url: "/", icon: Building2 }];

export default function AppLayout({ children }: { children: ReactNode }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const me = useMe();

  return (
    <DashboardLayout
      subtitle="Landlord"
      homeHref="/"
      nav={nav}
      footer={
        <NavUser
          user={me.data ? { name: me.data.name, subtitle: me.data.email ?? undefined } : undefined}
          onSignOut={async () => {
            await supabase().auth.signOut();
            queryClient.clear();
            router.replace("/sign-in");
            router.refresh();
          }}
        />
      }
    >
      {children}
    </DashboardLayout>
  );
}
