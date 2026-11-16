"use client";

import { Map, MapControls, MapMarker, MarkerContent, MarkerLabel } from "@rentfit/ui/map/map";

export interface CityPoint {
  slug: string;
  name: string;
  /** [lng, lat] */
  center: readonly [number, number] | readonly number[];
}

/** A map of India with one labelled marker per supported city. Clicking a marker calls `onSelect`. */
export function CitiesMap({
  cities,
  onSelect,
  className,
}: {
  cities: readonly CityPoint[];
  onSelect?: (slug: string) => void;
  className?: string;
}) {
  return (
    <div className={className ?? "h-[420px] overflow-hidden rounded-xl border"}>
      <Map center={[80.5, 19.5]} zoom={4.2} attributionControl={{ compact: true }}>
        <MapControls />
        {cities.map((c) => (
          <MapMarker
            key={c.slug}
            longitude={Number(c.center[0])}
            latitude={Number(c.center[1])}
            onClick={() => onSelect?.(c.slug)}
          >
            <MarkerContent>
              <span
                data-testid={`city-marker-${c.slug}`}
                className="block size-4 rounded-full border-2 border-background bg-primary shadow"
              />
              <MarkerLabel position="bottom">{c.name}</MarkerLabel>
            </MarkerContent>
          </MapMarker>
        ))}
      </Map>
    </div>
  );
}
