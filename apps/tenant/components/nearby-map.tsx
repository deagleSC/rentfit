"use client";

import { Map, MapMarker, MarkerContent, MarkerTooltip } from "@rentfit/ui/map/map";

import type { ListingDetail } from "@/lib/homes";

const lngLat = (p: readonly number[]): [number, number] => [Number(p[0]), Number(p[1])];

export function NearbyMap({ d }: { d: ListingDetail }) {
  const [lng, lat] = lngLat(d.location);
  return (
    <div className="h-64 overflow-hidden rounded-xl border">
      <Map center={[lng, lat]} zoom={13.5} attributionControl={{ compact: true }}>
        <MapMarker longitude={lng} latitude={lat}>
          <MarkerContent>
            <span className="block size-4 rounded-full border-2 border-background bg-primary shadow" />
          </MarkerContent>
          <MarkerTooltip>This home</MarkerTooltip>
        </MapMarker>
        {d.nearby.map((p) => (
          <MapMarker key={p.id} longitude={lngLat(p.location)[0]} latitude={lngLat(p.location)[1]}>
            <MarkerContent>
              <span className="block size-2.5 rounded-full border border-background bg-secondary shadow" />
            </MarkerContent>
            <MarkerTooltip>{p.name}</MarkerTooltip>
          </MapMarker>
        ))}
      </Map>
    </div>
  );
}
