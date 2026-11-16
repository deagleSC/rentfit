"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@rentfit/ui/components/card";

import { inr, useRentSuggestion, type Listing } from "@/lib/listings";

export function RentCard({ listing }: { listing: Listing }) {
  const ready = Boolean(listing.bhk && listing.location);
  const q = useRentSuggestion(listing.id, ready);
  if (!ready || !q.data) return null;
  const s = q.data;
  const hasRange = s.p25 != null && s.p75 != null;
  const span = hasRange ? Math.max(1, (s.p75 as number) - (s.p25 as number)) : 1;
  const lo = hasRange ? (s.p25 as number) - span : 0;
  const hi = hasRange ? (s.p75 as number) + span : 1;
  const pct = (v: number) => `${Math.min(100, Math.max(0, ((v - lo) / (hi - lo)) * 100))}%`;
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">Rent check</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <p>{s.text}</p>
        {hasRange ? (
          <div aria-hidden className="relative h-2 rounded-full bg-muted">
            <div className="absolute inset-y-0 rounded-full bg-primary/30" style={{ left: pct(s.p25 as number), right: `calc(100% - ${pct(s.p75 as number)})` }} />
            {listing.rent ? (
              <div className="absolute -top-1 size-4 -translate-x-1/2 rounded-full border-2 border-background bg-primary" style={{ left: pct(listing.rent) }} />
            ) : null}
          </div>
        ) : null}
        {s.position && listing.rent ? (
          <p className="text-muted-foreground">
            Your rent {inr(listing.rent)} is {s.position === "within" ? "within" : s.position} the usual range.
          </p>
        ) : null}
      </CardContent>
    </Card>
  );
}
