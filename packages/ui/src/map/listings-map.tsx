"use client";

import { Map, MapControls, MapMarker, MarkerContent, MarkerTooltip } from "@rentfit/ui/map/map";

export interface ListingPin {
  id: string;
  /** [lng, lat] */
  location: readonly [number, number] | readonly number[];
  bhk: number;
  rent: number;
  locality: string;
}

/** "₹35k", "₹1.2L": short enough for a pin. */
export function shortRent(rent: number): string {
  if (rent >= 100_000) return `₹${(rent / 100_000).toFixed(rent % 100_000 ? 1 : 0)}L`;
  return `₹${Math.round(rent / 1000)}k`;
}

/** A city map with one rent pill per listing. */
export function ListingsMap({
  center,
  zoom = 11,
  pins,
  onSelect,
  className,
}: {
  center: readonly [number, number] | readonly number[];
  zoom?: number;
  pins: readonly ListingPin[];
  onSelect?: (id: string) => void;
  className?: string;
}) {
  return (
    <div className={className ?? "h-[420px] overflow-hidden rounded-xl border"}>
      <Map center={[Number(center[0]), Number(center[1])]} zoom={zoom} attributionControl={{ compact: true }}>
        <MapControls />
        {pins.map((p) => (
          <MapMarker
            key={p.id}
            longitude={Number(p.location[0])}
            latitude={Number(p.location[1])}
            onClick={() => onSelect?.(p.id)}
          >
            <MarkerContent>
              <span
                data-testid="listing-pin"
                className="block rounded-full border border-background bg-primary px-2 py-0.5 text-xs font-medium text-primary-foreground tabular-nums shadow"
              >
                {shortRent(p.rent)}
              </span>
            </MarkerContent>
            <MarkerTooltip>
              {p.bhk} BHK · {p.locality}
            </MarkerTooltip>
          </MapMarker>
        ))}
      </Map>
    </div>
  );
}
