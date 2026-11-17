import { RentfitMark } from "@rentfit/ui/blocks/rentfit-mark";
import { Button } from "@rentfit/ui/components/button";
import Link from "next/link";
import type { ReactNode } from "react";

import { LANDLORD_APP, TENANT_APP } from "./links";

const NAV = [
  { href: "/tenants", label: "For tenants" },
  { href: "/landlords", label: "For landlords" },
];

export function SiteHeader() {
  return (
    <header className="sticky top-0 z-20 border-b bg-background/85 backdrop-blur">
      <div className="mx-auto flex h-14 max-w-6xl items-center justify-between gap-4 px-4">
        <Link href="/" className="flex items-center gap-2 font-semibold">
          <RentfitMark size={28} className="size-7" />
          RentFit
        </Link>
        <nav aria-label="Main" className="flex items-center gap-1 text-sm">
          {NAV.map((n) => (
            <Link key={n.href} href={n.href} className="hidden rounded-md px-3 py-2 text-muted-foreground hover:text-foreground sm:block">
              {n.label}
            </Link>
          ))}
          <Button asChild size="sm" className="ml-1">
            <a href={TENANT_APP}>Find a home</a>
          </Button>
        </nav>
      </div>
    </header>
  );
}

export function SiteFooter() {
  return (
    <footer className="border-t">
      <div className="mx-auto grid max-w-6xl gap-8 px-4 py-10 text-sm sm:grid-cols-[1fr_auto_auto]">
        <div className="space-y-2">
          <div className="flex items-center gap-2 font-semibold">
            <RentfitMark size={24} className="size-6" /> RentFit
          </div>
          <p className="max-w-sm text-muted-foreground">
            Rental search by conversation, for Bengaluru and Mumbai. Listings in the app today are sample data.
          </p>
        </div>
        <nav aria-label="Product" className="flex flex-col gap-2">
          <Link href="/tenants" className="hover:underline">For tenants</Link>
          <Link href="/landlords" className="hover:underline">For landlords</Link>
          <a href={TENANT_APP} className="hover:underline">Tenant app</a>
          <a href={LANDLORD_APP} className="hover:underline">Landlord app</a>
        </nav>
        <nav aria-label="Legal" className="flex flex-col gap-2">
          <Link href="/privacy" className="hover:underline">Privacy</Link>
          <Link href="/terms" className="hover:underline">Terms</Link>
          <span className="text-muted-foreground">Map data © OpenStreetMap contributors</span>
        </nav>
      </div>
    </footer>
  );
}

export function Section({ id, eyebrow, title, intro, children, className }: {
  id?: string; eyebrow?: string; title: string; intro?: ReactNode; children?: ReactNode; className?: string;
}) {
  return (
    <section id={id} className={className ?? "mx-auto max-w-6xl px-4 py-16 sm:py-20"}>
      <div className="max-w-2xl space-y-3">
        {eyebrow && <p className="text-sm font-medium text-primary">{eyebrow}</p>}
        <h2 className="text-2xl font-semibold tracking-tight sm:text-3xl">{title}</h2>
        {intro && <p className="text-muted-foreground">{intro}</p>}
      </div>
      {children && <div className="mt-10">{children}</div>}
    </section>
  );
}

export function Feature({ icon, title, children }: { icon: ReactNode; title: string; children: ReactNode }) {
  return (
    <div className="space-y-2 rounded-xl border bg-card p-5">
      <div className="flex size-9 items-center justify-center rounded-lg bg-primary/10 text-primary [&_svg]:size-5">{icon}</div>
      <h3 className="font-medium">{title}</h3>
      <p className="text-sm leading-relaxed text-muted-foreground">{children}</p>
    </div>
  );
}

export function Steps({ items }: { items: { title: string; body: string }[] }) {
  return (
    <ol className="grid gap-4 md:grid-cols-3">
      {items.map((s, i) => (
        <li key={s.title} className="rounded-xl border bg-card p-5">
          <span className="text-sm font-semibold text-primary tabular-nums">Step {i + 1}</span>
          <h3 className="mt-1 font-medium">{s.title}</h3>
          <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{s.body}</p>
        </li>
      ))}
    </ol>
  );
}

export function Prose({ title, updated, children }: { title: string; updated: string; children: ReactNode }) {
  return (
    <article className="mx-auto max-w-2xl px-4 py-14">
      <h1 className="text-3xl font-semibold tracking-tight">{title}</h1>
      <p className="mt-2 text-sm text-muted-foreground">Last updated {updated}</p>
      <div className="mt-8 space-y-4 text-[15px] leading-relaxed [&_h2]:mt-8 [&_h2]:text-lg [&_h2]:font-semibold [&_li]:ml-5 [&_li]:list-disc [&_a]:text-primary [&_a]:underline">
        {children}
      </div>
    </article>
  );
}
