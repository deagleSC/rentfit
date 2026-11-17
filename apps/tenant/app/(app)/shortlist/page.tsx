"use client";

import { messageFor } from "@rentfit/api-client";
import { PageHeader } from "@rentfit/ui/blocks/dashboard-layout";
import { EmptyState, ErrorState, PageSkeleton } from "@rentfit/ui/blocks/states";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@rentfit/ui/components/table";
import { Heart } from "lucide-react";
import Link from "next/link";

import { ListingCardView } from "@/components/search/listing-card";
import { FURNISHING, inr, useShortlist } from "@/lib/homes";
import type { ListingCard } from "@/lib/search";

export default function ShortlistPage() {
  const q = useShortlist();
  if (q.isError) return <ErrorState message={messageFor(q.error)} />;
  if (q.isPending) return <PageSkeleton />;
  const cards = q.data as unknown as ListingCard[];
  return (
    <>
      <PageHeader title="Shortlist" description="Homes you've saved, side by side." />
      {cards.length === 0 ? (
        <EmptyState icon={<Heart />} title="Nothing shortlisted yet" description="Tap the heart on a search result to keep it here." />
      ) : (
        <div className="space-y-6">
          <div className="overflow-x-auto rounded-xl border bg-card">
            <Table aria-label="Compare shortlisted homes">
              <TableHeader>
                <TableRow>
                  <TableHead>Home</TableHead>
                  <TableHead className="text-right">Rent</TableHead>
                  <TableHead className="text-right">Deposit</TableHead>
                  <TableHead>Furnishing</TableHead>
                  <TableHead className="text-right">Metro</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {cards.map((c) => (
                  <TableRow key={c.id}>
                    <TableCell>
                      <Link href={`/listings/${c.id}`} className="font-medium hover:underline">{c.bhk} BHK, {c.locality}</Link>
                    </TableCell>
                    <TableCell className="text-right tabular-nums">{inr(c.rent)}</TableCell>
                    <TableCell className="text-right tabular-nums">{inr(c.deposit)}</TableCell>
                    <TableCell>{FURNISHING[c.furnishing] ?? c.furnishing}</TableCell>
                    <TableCell className="text-right tabular-nums">
                      {c.metro ? (c.metro.metres < 1000 ? `${c.metro.metres} m` : `${(c.metro.metres / 1000).toFixed(1)} km`) : "—"}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
          <div className="grid gap-3 md:grid-cols-2">
            {cards.map((c) => <ListingCardView key={c.id} card={c} />)}
          </div>
        </div>
      )}
    </>
  );
}
