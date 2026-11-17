import { RentfitMark } from "@rentfit/ui/blocks/rentfit-mark";
import { cn } from "@rentfit/ui/lib/utils";
import Image, { type StaticImageData } from "next/image";
import Link from "next/link";
import type { ReactNode } from "react";

import { LANDLORD_APP, TENANT_APP } from "./links";

export function SiteHeader() {
  return (
    <header className="border-b">
      <div className="mx-auto flex h-14 max-w-6xl items-center justify-between gap-4 px-4 sm:px-6">
        <Link href="/" className="flex items-center gap-2 font-medium">
          <RentfitMark size={24} className="size-6 shadow-none" />
          RentFit
        </Link>
        <nav aria-label="Main" className="flex items-center gap-5 text-sm">
          <Link href="/tenants" className="hidden text-muted-foreground hover:text-foreground sm:block">Renting</Link>
          <Link href="/landlords" className="hidden text-muted-foreground hover:text-foreground sm:block">Listing</Link>
          <a href={TENANT_APP} className="font-medium text-primary hover:underline">Sign in</a>
        </nav>
      </div>
    </header>
  );
}

export function SiteFooter() {
  return (
    <footer className="border-t text-sm text-muted-foreground">
      <div className="mx-auto flex max-w-6xl flex-col gap-3 px-4 py-8 sm:flex-row sm:items-center sm:justify-between sm:px-6">
        <p>RentFit · Bengaluru and Mumbai · Listings are sample data for now.</p>
        <nav aria-label="Footer" className="flex flex-wrap gap-x-5 gap-y-1">
          <a href={TENANT_APP} className="hover:text-foreground">Tenant app</a>
          <a href={LANDLORD_APP} className="hover:text-foreground">Landlord app</a>
          <Link href="/privacy" className="hover:text-foreground">Privacy</Link>
          <Link href="/terms" className="hover:text-foreground">Terms</Link>
          <span>Map data © OpenStreetMap contributors</span>
        </nav>
      </div>
    </footer>
  );
}

/** A plain browser frame around a product screenshot. */
export function Shot({ src, alt, priority, className }: {
  src: StaticImageData; alt: string; priority?: boolean; className?: string;
}) {
  return (
    <div className={cn("overflow-hidden rounded-xl border bg-card shadow-[0_24px_60px_-30px_rgb(0_0_0/0.35)]", className)}>
      <div className="flex h-8 items-center gap-1.5 border-b bg-muted/60 px-3" aria-hidden>
        <span className="size-2.5 rounded-full bg-foreground/15" />
        <span className="size-2.5 rounded-full bg-foreground/15" />
        <span className="size-2.5 rounded-full bg-foreground/15" />
      </div>
      <Image src={src} alt={alt} priority={priority} sizes="(min-width: 1152px) 1100px, 100vw" className="h-auto w-full" />
    </div>
  );
}

/** Rows with hairline dividers: a short label on the left, the detail on the right. */
export function Rows({ items }: { items: { term: ReactNode; detail: ReactNode }[] }) {
  return (
    <dl className="divide-y border-y">
      {items.map((r, i) => (
        <div key={i} className="grid gap-1 py-5 sm:grid-cols-[minmax(0,1fr)_minmax(0,2fr)] sm:gap-10">
          <dt className="font-medium">{r.term}</dt>
          <dd className="text-muted-foreground">{r.detail}</dd>
        </div>
      ))}
    </dl>
  );
}

export function Container({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn("mx-auto max-w-6xl px-4 sm:px-6", className)}>{children}</div>;
}

export function Prose({ title, updated, children }: { title: string; updated: string; children: ReactNode }) {
  return (
    <article className="mx-auto max-w-3xl px-4 py-14 sm:px-6">
      <h1 className="display text-4xl sm:text-5xl">{title}</h1>
      <p className="mt-3 text-sm text-muted-foreground">Last updated {updated}</p>
      <div className="mt-10 space-y-4 text-[15px] leading-relaxed [&_a]:text-primary [&_a]:underline [&_h2]:mt-10 [&_h2]:font-medium [&_li]:ml-5 [&_li]:list-disc">
        {children}
      </div>
    </article>
  );
}
