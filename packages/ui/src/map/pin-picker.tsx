"use client";

import { Map, MapControls, MapMarker, MarkerContent, useMap } from "@rentfit/ui/map/map";
import { useEffect } from "react";

export interface LatLng {
  lat: number;
  lng: number;
}

function ClickToPlace({ onPick }: { onPick: (p: LatLng) => void }) {
  const { map } = useMap();
  useEffect(() => {
    if (!map) return;
    const handler = (e: { lngLat: { lng: number; lat: number } }) => onPick({ lat: e.lngLat.lat, lng: e.lngLat.lng });
    map.on("click", handler);
    map.getCanvas().style.cursor = "crosshair";
    return () => {
      map.off("click", handler);
    };
  }, [map, onPick]);
  return null;
}

/** Click the map or drag the pin to set a location. `center` is used until a pin exists. */
export function PinPicker({
  value,
  center,
  zoom = 12,
  onChange,
  className,
}: {
  value: LatLng | null;
  center: [number, number];
  zoom?: number;
  onChange: (p: LatLng) => void;
  className?: string;
}) {
  const start: [number, number] = value ? [value.lng, value.lat] : center;
  return (
    <div className={className ?? "h-72 overflow-hidden rounded-xl border"}>
      <Map center={start} zoom={value ? 15 : zoom} attributionControl={{ compact: true }}>
        <MapControls showLocate onLocate={(c) => onChange({ lat: c.latitude, lng: c.longitude })} />
        <ClickToPlace onPick={onChange} />
        {value ? (
          <MapMarker longitude={value.lng} latitude={value.lat} draggable onDragEnd={(p) => onChange(p)}>
            <MarkerContent>
              <span
                data-testid="listing-pin"
                className="block size-5 rounded-full border-2 border-background bg-primary shadow-md"
              />
            </MarkerContent>
          </MapMarker>
        ) : null}
      </Map>
    </div>
  );
}
