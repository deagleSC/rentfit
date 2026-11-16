"use client";

import { messageFor } from "@rentfit/api-client";
import { PageHeader } from "@rentfit/ui/blocks/dashboard-layout";
import { EmptyState, ErrorState, PageSkeleton } from "@rentfit/ui/blocks/states";
import { Button } from "@rentfit/ui/components/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@rentfit/ui/components/table";
import { Building2, MessageSquarePlus } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { toast } from "sonner";

import { RowActions } from "@/components/listing/row-actions";
import { StatusBadge } from "@/components/listing/status-badge";
import { useMe } from "@/lib/api";
import { inr, useCreateListing, useListings } from "@/lib/listings";

export default function ListingsPage() {
  const me = useMe();
  const listings = useListings();
  const create = useCreateListing();
  const router = useRouter();

  if (me.isError) return <ErrorState message={messageFor(me.error)} />;
  if (listings.isError) return <ErrorState message={messageFor(listings.error)} />;
  if (me.isPending || listings.isPending) return <PageSkeleton />;

  const newListing = (
    <Button
      disabled={create.isPending}
      onClick={() =>
        create.mutate(undefined, {
          onSuccess: (l) => router.push(`/listings/${l.id}`),
          onError: (e) => toast.error(messageFor(e)),
        })
      }
    >
      <MessageSquarePlus />
      New listing
    </Button>
  );

  return (
    <>
      <PageHeader title="Your listings" description={`Signed in as ${me.data.name}`} actions={listings.data.length ? newListing : null} />
      {listings.data.length === 0 ? (
        <EmptyState
          icon={<Building2 />}
          title="No listings yet"
          description="Describe your flat in chat and RentFit builds the listing for you."
        >
          {newListing}
        </EmptyState>
      ) : (
        <div className="overflow-hidden rounded-xl border bg-card shadow-sm">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Listing</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="hidden sm:table-cell">Photos</TableHead>
                <TableHead className="text-right">Rent</TableHead>
                <TableHead className="w-12">
                  <span className="sr-only">Actions</span>
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {listings.data.map((l) => (
                <TableRow key={l.id}>
                  <TableCell>
                    <Link href={`/listings/${l.id}`} className="font-medium hover:underline">
                      {l.title || (l.bhk ? `${l.bhk} BHK` : "Untitled draft")}
                    </Link>
                    <div className="text-xs text-muted-foreground">{l.city ?? "City not set"}</div>
                  </TableCell>
                  <TableCell>
                    <StatusBadge status={l.status} />
                  </TableCell>
                  <TableCell className="hidden tabular-nums sm:table-cell">{l.photo_count}</TableCell>
                  <TableCell className="text-right tabular-nums">{inr(l.rent)}</TableCell>
                  <TableCell>
                    <RowActions listing={l} />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </>
  );
}
