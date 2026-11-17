"use client";

import { Badge } from "@rentfit/ui/components/badge";
import { Button } from "@rentfit/ui/components/button";
import { cn } from "@rentfit/ui/lib/utils";
import { Heart, Home, Route, TrainFront } from "lucide-react";
import Link from "next/link";

import { FURNISHING, shortInr, useToggleShortlist } from "@/lib/homes";
import type { ListingCard } from "@/lib/search";

function metro(m: NonNullable<ListingCard["metro"]>) {
  return m.metres < 1000 ? `${m.metres} m` : `${(m.metres / 1000).toFixed(1)} km`;
}

/** A search result. Hovering highlights its map pin; the heart toggles the shortlist. */
export function ListingCardView({
  card,
  index,
  active,
  onHover,
}: {
  card: ListingCard;
  index?: number;
  active?: boolean;
  onHover?: (id: string | null) => void;
}) {
  const toggle = useToggleShortlist();
  const on = toggle.isPending ? !!toggle.variables?.on : card.shortlisted;
  return (
    <div
      id={`card-${card.id}`}
      data-testid="listing-card"
      onMouseEnter={() => onHover?.(card.id)}
      onMouseLeave={() => onHover?.(null)}
      className={cn(
        "group relative flex gap-3 rounded-xl border bg-card p-2 shadow-sm transition-colors",
        active && "border-primary ring-1 ring-primary",
      )}
    >
      <Link href={`/listings/${card.id}`} className="flex min-w-0 flex-1 gap-3">
        <div className="relative size-20 shrink-0 overflow-hidden rounded-lg bg-muted">
          {card.thumb_url ? (
            // eslint-disable-next-line @next/next/no-img-element -- signed storage URLs, sized by the browser resize
            <img src={card.thumb_url} alt="" className="size-full object-cover" loading="lazy" />
          ) : (
            <Home className="m-auto mt-6 size-8 text-muted-foreground" />
          )}
          {index != null && (
            <span className="absolute left-1 top-1 rounded bg-background/90 px-1.5 text-xs font-medium">{index}</span>
          )}
        </div>
        <div className="min-w-0 flex-1 space-y-1">
          <div className="flex items-baseline gap-2">
            <span className="font-semibold tabular-nums">{shortInr(card.rent)}</span>
            <span className="truncate text-sm text-muted-foreground">
              {card.bhk} BHK · {card.locality}
            </span>
          </div>
          <div className="flex flex-wrap gap-1">
            <Badge variant="secondary">{FURNISHING[card.furnishing] ?? card.furnishing}</Badge>
            {card.metro && (
              <Badge variant="outline" className="gap-1">
                <TrainFront className="size-3" />
                {metro(card.metro)}
              </Badge>
            )}
            {card.commute && (
              <Badge variant="outline" className="gap-1" title={card.commute.provider === "haversine" ? "Estimate" : "Route time"}>
                <Route className="size-3" />
                {card.commute.minutes} min{card.commute.provider === "haversine" ? "*" : ""}
              </Badge>
            )}
          </div>
          {card.deposit != null && (
            <div className="text-xs text-muted-foreground">Deposit {shortInr(card.deposit)}</div>
          )}
        </div>
      </Link>
      <Button
        variant="ghost"
        size="icon"
        className="shrink-0 self-start"
        aria-label={on ? "Remove from shortlist" : "Add to shortlist"}
        aria-pressed={on}
        onClick={() => toggle.mutate({ id: card.id, on: !on })}
      >
        <Heart className={cn("size-4", on && "fill-primary text-primary")} />
      </Button>
    </div>
  );
}
