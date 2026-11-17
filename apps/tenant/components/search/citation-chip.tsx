"use client";

import { Popover, PopoverContent, PopoverTrigger } from "@rentfit/ui/components/popover";
import { Home, MapPinned } from "lucide-react";
import Link from "next/link";

import type { Ref } from "@/lib/search";

/** A source for a claim: a listing (opens it) or an area note (shows its text and source). */
export function CitationChip({ r, n }: { r: Ref; n: number }) {
  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          data-testid="citation"
          className="mx-0.5 inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-primary/10 px-1.5 align-middle text-[11px] font-medium text-primary hover:bg-primary/20"
          aria-label={`Source ${n}: ${r.label}`}
        >
          {n}
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-72 text-sm" data-testid="citation-source">
        {r.kind === "listing" ? (
          <div className="space-y-2">
            <div className="flex items-center gap-2 font-medium">
              <Home className="size-4" /> {r.label}
            </div>
            <Link href={`/listings/${r.id}`} className="text-primary underline-offset-4 hover:underline">
              Open listing
            </Link>
          </div>
        ) : (
          <div className="space-y-2">
            <div className="flex items-center gap-2 font-medium">
              <MapPinned className="size-4" /> {r.label}
            </div>
            <p className="text-muted-foreground">{r.text}</p>
            <p className="text-xs text-muted-foreground">© OpenStreetMap contributors</p>
          </div>
        )}
      </PopoverContent>
    </Popover>
  );
}
