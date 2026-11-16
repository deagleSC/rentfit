"use client";

import { messageFor } from "@rentfit/api-client";
import { PageHeader } from "@rentfit/ui/blocks/dashboard-layout";
import { ErrorState, PageSkeleton } from "@rentfit/ui/blocks/states";
import { use, useEffect, useState } from "react";

import { ListingActions } from "@/components/listing/actions";
import { ChatPanel } from "@/components/listing/chat-panel";
import { EditSheet } from "@/components/listing/edit-sheet";
import { PhotosPanel } from "@/components/listing/photos-panel";
import { PinPanel } from "@/components/listing/pin-panel";
import { PreviewCard } from "@/components/listing/preview-card";
import { RentCard } from "@/components/listing/rent-card";
import { StatusBadge } from "@/components/listing/status-badge";
import { useLocalities } from "@/lib/api";
import { useChat, useListing, type Change } from "@/lib/listings";

export default function ListingPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const listing = useListing(id);
  const chat = useChat(id);
  const localities = useLocalities(listing.data?.city);
  const [highlight, setHighlight] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (!highlight.size) return;
    const t = setTimeout(() => setHighlight(new Set()), 2500);
    return () => clearTimeout(t);
  }, [highlight]);

  if (listing.isError) return <ErrorState message={messageFor(listing.error)} />;
  if (listing.isPending) return <PageSkeleton />;
  const l = listing.data;
  const localityName = localities.data?.find((x) => x.id === l.locality_id)?.name ?? null;
  const onChanges = (c: Change[]) => setHighlight(new Set(c.map((x) => x.field)));

  return (
    <>
      <PageHeader
        title={l.title || (l.bhk ? `${l.bhk} BHK${localityName ? ` in ${localityName}` : ""}` : "New listing")}
        description={<StatusBadge status={l.status} />}
        actions={
          <div className="flex gap-2">
            <EditSheet listing={l} onChanges={onChanges} />
            <ListingActions listing={l} />
          </div>
        }
      />
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
        <ChatPanel id={id} onChanges={onChanges} />
        <div className="space-y-4">
          <PreviewCard listing={l} localityName={localityName} highlight={highlight} missing={chat.data?.missing ?? []} />
          <RentCard listing={l} />
          <PinPanel listing={l} localityName={localityName} />
          <PhotosPanel listing={l} />
        </div>
      </div>
    </>
  );
}
