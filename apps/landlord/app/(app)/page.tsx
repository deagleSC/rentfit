"use client";

import { messageFor } from "@rentfit/api-client";
import { PageHeader } from "@rentfit/ui/blocks/dashboard-layout";
import { EmptyState, ErrorState, PageSkeleton } from "@rentfit/ui/blocks/states";
import { Building2 } from "lucide-react";
import dynamic from "next/dynamic";

import { useCities, useMe } from "@/lib/api";

// MapLibre needs the browser.
const CitiesMap = dynamic(() => import("@rentfit/ui/map/cities-map").then((m) => m.CitiesMap), { ssr: false });

export default function ListingsPage() {
  const me = useMe();
  const cities = useCities();

  if (me.isError) return <ErrorState message={messageFor(me.error)} />;
  if (cities.isError) return <ErrorState message={messageFor(cities.error)} />;
  if (me.isPending || cities.isPending) return <PageSkeleton />;

  return (
    <>
      <PageHeader title="Your listings" description={`Signed in as ${me.data.name}`} />
      <EmptyState
        icon={<Building2 />}
        title="No listings yet"
        description="Soon you'll describe your flat in chat and RentFit will build the listing for you."
      />
      <section className="mt-6" aria-label="Cities we cover">
        <h2 className="mb-2 text-sm font-medium text-muted-foreground">
          RentFit covers {cities.data.map((c) => c.name).join(", ")}
        </h2>
        <CitiesMap cities={cities.data} />
      </section>
    </>
  );
}
