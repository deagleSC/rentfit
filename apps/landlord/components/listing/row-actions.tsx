"use client";

import { messageFor } from "@rentfit/api-client";
import { Button } from "@rentfit/ui/components/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@rentfit/ui/components/dropdown-menu";
import { MoreHorizontal } from "lucide-react";
import Link from "next/link";
import { toast } from "sonner";

import { useTransition, type Action, type Listing } from "@/lib/listings";

const ACTIONS: Record<Listing["status"], { action: Action; label: string; done: string }[]> = {
  draft: [],
  published: [
    { action: "pause", label: "Pause", done: "Paused" },
    { action: "let", label: "Mark as let", done: "Marked as let" },
  ],
  paused: [
    { action: "resume", label: "Resume", done: "Published again" },
    { action: "let", label: "Mark as let", done: "Marked as let" },
  ],
  let: [],
};

/** Status changes from the listings table. Publishing a draft happens on its page, where the
 * checklist explains what is missing. */
export function RowActions({ listing }: { listing: Listing }) {
  const t = useTransition(listing.id);
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" aria-label="Listing actions" disabled={t.isPending}>
          <MoreHorizontal />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuItem asChild>
          <Link href={`/listings/${listing.id}`}>{listing.status === "draft" ? "Continue editing" : "Open"}</Link>
        </DropdownMenuItem>
        {ACTIONS[listing.status].map((a) => (
          <DropdownMenuItem
            key={a.action}
            onSelect={() =>
              t.mutate(a.action, {
                onSuccess: () => toast.success(a.done),
                onError: (e) => toast.error(messageFor(e)),
              })
            }
          >
            {a.label}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
