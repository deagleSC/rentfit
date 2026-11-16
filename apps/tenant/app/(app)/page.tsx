"use client";

import { messageFor } from "@rentfit/api-client";
import { PageHeader } from "@rentfit/ui/blocks/dashboard-layout";
import { ErrorState, PageSkeleton } from "@rentfit/ui/blocks/states";
import dynamic from "next/dynamic";

import { useCities, useMe } from "@/lib/api";

// MapLibre needs the browser.
const CitiesMap = dynamic(() => import("@rentfit/ui/map/cities-map").then((m) => m.CitiesMap), { ssr: false });

export default function SearchPage() {
  const me = useMe();
  const cities = useCities();

  if (me.isError) return <ErrorState message={messageFor(me.error)} />;
  if (cities.isError) return <ErrorState message={messageFor(cities.error)} />;
  if (me.isPending || cities.isPending) return <PageSkeleton />;

  return (
    <>
      <PageHeader
        title="Find a home"
        description="Chat search is coming soon. For now, here are the cities RentFit covers."
      />
      <CitiesMap cities={cities.data} className="h-[calc(100vh-12rem)] min-h-[360px] overflow-hidden rounded-xl border" />
    </>
  );
}
