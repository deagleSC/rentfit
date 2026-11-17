"use client";

import { messageFor, readSSEEvents } from "@rentfit/api-client";
import { PageHeader } from "@rentfit/ui/blocks/dashboard-layout";
import { EmptyState, ErrorState, PageSkeleton } from "@rentfit/ui/blocks/states";
import { Badge } from "@rentfit/ui/components/badge";
import { Button } from "@rentfit/ui/components/button";
import { Bookmark, Search, Trash2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { env } from "@/lib/env";
import { useDeleteSaved, useSavedSearches, type SavedSearch } from "@/lib/homes";
import { supabase } from "@/lib/supabase";

/** Opening a saved search starts a new search chat from its filters (no alerts in v1). */
async function openSaved(s: SavedSearch): Promise<string> {
  const token = (await supabase().auth.getSession()).data.session?.access_token;
  const res = await fetch(`${env.apiUrl}/v1/tenant/search/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    body: JSON.stringify({ filters: s.filters }),
  });
  let chatId = "";
  let error = "";
  await readSSEEvents(res, (name, data) => {
    if (name === "done") chatId = (data as { chat_id: string }).chat_id;
    if (name === "error") error = (data as { message: string }).message;
  });
  if (!chatId) throw new Error(error || "Could not open the search.");
  return chatId;
}

export default function SavedPage() {
  const q = useSavedSearches();
  const del = useDeleteSaved();
  const router = useRouter();
  const [opening, setOpening] = useState<string | null>(null);
  if (q.isError) return <ErrorState message={messageFor(q.error)} />;
  if (q.isPending) return <PageSkeleton />;
  return (
    <>
      <PageHeader title="Saved searches" description="Reopen a search with the same filters." />
      {q.data.length === 0 ? (
        <EmptyState icon={<Bookmark />} title="No saved searches" description="Use “Save search” above your filters to keep one here." />
      ) : (
        <ul className="space-y-3">
          {q.data.map((s) => (
            <li key={s.id} className="flex flex-col gap-3 rounded-xl border bg-card p-4 sm:flex-row sm:items-center sm:justify-between">
              <div className="min-w-0 space-y-2">
                <div className="font-medium">{s.name}</div>
                <div className="flex flex-wrap gap-1.5">
                  {s.chips.map((c) => <Badge key={c.field} variant="secondary">{c.label}</Badge>)}
                </div>
              </div>
              <div className="flex shrink-0 gap-2">
                <Button
                  disabled={opening !== null}
                  onClick={() => {
                    setOpening(s.id);
                    openSaved(s as unknown as SavedSearch)
                      .then((id) => router.push(`/search/${id}`))
                      .catch((e: unknown) => toast.error(messageFor(e)))
                      .finally(() => setOpening(null));
                  }}
                >
                  <Search /> {opening === s.id ? "Opening…" : "Open"}
                </Button>
                <Button variant="ghost" size="icon" aria-label={`Delete ${s.name}`} onClick={() => del.mutate(s.id)}>
                  <Trash2 />
                </Button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
