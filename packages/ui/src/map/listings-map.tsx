"use client";

import { useEffect, useRef } from "react";

import { cn } from "@rentfit/ui/lib/utils";
import { Map, MapControls, MapMarker, MarkerContent, MarkerTooltip, useMap } from "@rentfit/ui/map/map";

export interface ListingPin {
  id: string;
  /** [lng, lat] */
  location: readonly [number, number] | readonly number[];
  bhk: number;
  rent: number;
  locality: string;
}

export type Bounds = [number, number, number, number]; // west, south, east, north

/** "₹35k", "₹1.2L": short enough for a pin. */
export function shortRent(rent: number): string {
  if (rent >= 100_000) return `₹${+(rent / 100_000).toFixed(1)}L`;
  return `₹${Math.round(rent / 1000)}k`;
}

/** Fits the view to the pins when they change, and reports the visible bounds after each move. */
function MapEffects({ pins, fit, onBoundsChange }: {
  pins: readonly ListingPin[];
  fit: boolean;
  onBoundsChange?: (b: Bounds) => void;
}) {
  const { map } = useMap();
  const cb = useRef(onBoundsChange);
  cb.current = onBoundsChange;
  const key = pins.map((p) => p.id).join(",");

  useEffect(() => {
    if (!map || !fit || pins.length === 0) return;
    const lngs = pins.map((p) => Number(p.location[0]));
    const lats = pins.map((p) => Number(p.location[1]));
    map.fitBounds([[Math.min(...lngs), Math.min(...lats)], [Math.max(...lngs), Math.max(...lats)]],
                  { padding: 60, maxZoom: 14, duration: 600 });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- refit only when the set of pins changes
  }, [map, fit, key]);

  useEffect(() => {
    if (!map) return;
    const report = () => {
      const b = map.getBounds();
      cb.current?.([b.getWest(), b.getSouth(), b.getEast(), b.getNorth()]);
    };
    map.on("moveend", report);
    report();
    return () => {
      map.off("moveend", report);
    };
  }, [map]);
  return null;
}

/** A city map with one rent pill per listing. The active pin (hovered card) is highlighted. */
export function ListingsMap({
  center,
  zoom = 11,
  pins,
  activeId,
  onSelect,
  onHover,
  onBoundsChange,
  fitToPins = false,
  className,
  children,
}: {
  center: readonly [number, number] | readonly number[];
  zoom?: number;
  pins: readonly ListingPin[];
  activeId?: string | null;
  onSelect?: (id: string) => void;
  onHover?: (id: string | null) => void;
  onBoundsChange?: (b: Bounds) => void;
  fitToPins?: boolean;
  className?: string;
  children?: React.ReactNode;
}) {
  return (
    <div className={cn("relative", className ?? "h-[420px] overflow-hidden rounded-xl border")}>
      <Map center={[Number(center[0]), Number(center[1])]} zoom={zoom} attributionControl={{ compact: true }}>
        <MapControls />
        <MapEffects pins={pins} fit={fitToPins} onBoundsChange={onBoundsChange} />
        {pins.map((p) => {
          const active = p.id === activeId;
          return (
            <MapMarker
              key={p.id}
              longitude={Number(p.location[0])}
              latitude={Number(p.location[1])}
              onClick={() => onSelect?.(p.id)}
              onMouseEnter={() => onHover?.(p.id)}
              onMouseLeave={() => onHover?.(null)}
            >
              <MarkerContent>
                <span
                  data-testid="listing-pin"
                  data-active={active || undefined}
                  className={cn(
                    "block rounded-full border border-background px-2 py-0.5 text-xs font-medium tabular-nums shadow transition-transform",
                    active ? "z-10 scale-125 bg-foreground text-background" : "bg-primary text-primary-foreground",
                  )}
                >
                  {shortRent(p.rent)}
                </span>
              </MarkerContent>
              <MarkerTooltip>
                {p.bhk} BHK · {p.locality}
              </MarkerTooltip>
            </MapMarker>
          );
        })}
      </Map>
      {children}
    </div>
  );
}
