"use client";

import { DashboardLayout, type DashboardLayoutProps } from "@rentfit/ui/blocks/dashboard-layout";
import type { NavItem } from "@rentfit/ui/blocks/nav-main";
import { Bookmark, Heart, MessageSquare, Search, UserRound } from "lucide-react";

const nav: NavItem[] = [
  { title: "Search", url: "/", icon: Search },
  { title: "Shortlist", url: "/shortlist", icon: Heart },
  { title: "Saved searches", url: "/saved", icon: Bookmark },
  { title: "Enquiries", url: "/enquiries", icon: MessageSquare },
  { title: "Account", url: "/account", icon: UserRound },
];

/** Tenant app shell. Client-side so the nav icons stay out of RSC props. */
export function TenantShell(props: Omit<DashboardLayoutProps, "nav" | "homeHref">) {
  return <DashboardLayout homeHref="/" nav={nav} {...props} />;
}
