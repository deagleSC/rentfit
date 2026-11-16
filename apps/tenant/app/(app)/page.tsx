"use client";

import { messageFor } from "@rentfit/api-client";
import { PageHeader } from "@rentfit/ui/blocks/dashboard-layout";
import { ErrorState, PageSkeleton } from "@rentfit/ui/blocks/states";
import { Tabs, TabsList, TabsTrigger } from "@rentfit/ui/components/tabs";
import dynamic from "next/dynamic";
import { useState } from "react";

import { useCities, useMapPins, useMe } from "@/lib/api";

// MapLibre needs the browser.
const ListingsMap = dynamic(() => import("@rentfit/ui/map/listings-map").then((m) => m.ListingsMap), { ssr: false });

export default function SearchPage() {
  const me = useMe();
  const cities = useCities();
  const [picked, setPicked] = useState<string>();
  const city = cities.data?.find((c) => c.slug === picked) ?? cities.data?.[0];
  const pins = useMapPins(city?.slug);

  if (me.isError) return <ErrorState message={messageFor(me.error)} />;
  if (cities.isError) return <ErrorState message={messageFor(cities.error)} />;
  if (me.isPending || cities.isPending || !city) return <PageSkeleton />;

  const count = pins.data?.length;
  return (
    <>
      <PageHeader
        title="Find a home"
        description={
          count === undefined
            ? "Loading listings…"
            : `${count} ${count === 1 ? "home" : "homes"} for rent in ${city.name}. Chat search is coming soon.`
        }
        actions={
          <Tabs value={city.slug} onValueChange={setPicked}>
            <TabsList>
              {cities.data.map((c) => (
                <TabsTrigger key={c.slug} value={c.slug}>
                  {c.name}
                </TabsTrigger>
              ))}
            </TabsList>
          </Tabs>
        }
      />
      {pins.isError ? (
        <ErrorState message={messageFor(pins.error)} />
      ) : (
        <ListingsMap
          key={city.slug}
          center={city.center}
          zoom={city.default_zoom}
          pins={pins.data ?? []}
          className="h-[calc(100vh-12rem)] min-h-[360px] overflow-hidden rounded-xl border"
        />
      )}
    </>
  );
}
