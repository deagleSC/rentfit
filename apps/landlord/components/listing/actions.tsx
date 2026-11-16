"use client";

import { ApiError, messageFor } from "@rentfit/api-client";
import { Button } from "@rentfit/ui/components/button";
import { Send } from "lucide-react";
import { toast } from "sonner";

import { FIELD_LABELS, useTransition, type Action, type Listing } from "@/lib/listings";

function reasonText(r: string): string {
  const [kind, detail] = r.split(":");
  if (kind === "missing") return `${FIELD_LABELS[detail ?? ""] ?? detail} is missing`;
  if (kind === "photos") return "add at least 3 photos";
  if (r === "location:outside_city") return "the pin is outside the city";
  if (r === "rent:too_low") return "the rent looks too low";
  return r;
}

export function ListingActions({ listing }: { listing: Listing }) {
  const t = useTransition(listing.id);
  const run = (action: Action, done: string) =>
    t.mutate(action, {
      onSuccess: () => toast.success(done),
      onError: (e) => {
        const reasons = e instanceof ApiError ? (e.details?.reasons as string[] | undefined) : undefined;
        toast.error(reasons?.length ? `Not ready: ${reasons.map(reasonText).join(", ")}.` : messageFor(e));
      },
    });
  switch (listing.status) {
    case "draft":
      return (
        <Button onClick={() => run("publish", "Published")} disabled={t.isPending}>
          <Send />
          Publish
        </Button>
      );
    case "published":
      return (
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => run("pause", "Paused")} disabled={t.isPending}>
            Pause
          </Button>
          <Button variant="outline" onClick={() => run("let", "Marked as let")} disabled={t.isPending}>
            Mark as let
          </Button>
        </div>
      );
    case "paused":
      return (
        <div className="flex gap-2">
          <Button onClick={() => run("resume", "Published again")} disabled={t.isPending}>
            Resume
          </Button>
          <Button variant="outline" onClick={() => run("let", "Marked as let")} disabled={t.isPending}>
            Mark as let
          </Button>
        </div>
      );
    default:
      return null;
  }
}
