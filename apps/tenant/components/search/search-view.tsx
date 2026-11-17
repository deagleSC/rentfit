"use client";

import { messageFor, unwrap } from "@rentfit/api-client";
import { Button } from "@rentfit/ui/components/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@rentfit/ui/components/dialog";
import { Input } from "@rentfit/ui/components/input";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@rentfit/ui/components/sheet";
import { ErrorState, PageSkeleton } from "@rentfit/ui/blocks/states";
import type { Bounds } from "@rentfit/ui/map/listings-map";
import { Bookmark, Map as MapIcon, ScanSearch } from "lucide-react";
import dynamic from "next/dynamic";
import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { api, useCities } from "@/lib/api";
import { useSaveSearch } from "@/lib/homes";
import { useSearch, type Chip, type ListingCard, type Pin, type SearchFilters, type Turn } from "@/lib/search";

import { ChatPanel } from "./chat-panel";
import { FilterChips } from "./filter-chips";

const ListingsMap = dynamic(() => import("@rentfit/ui/map/listings-map").then((m) => m.ListingsMap), { ssr: false });

/** Search split view (frontend plan §8.1): chat | map, chips above, cards ↔ pins synced. */
export function SearchView({ chatId }: { chatId?: string }) {
  const cities = useCities();
  const onChat = useCallback((id: string) => window.history.replaceState(null, "", `/search/${id}`), []);
  const { state, dispatch, send } = useSearch(onChat);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [mapOpen, setMapOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const bounds = useRef<Bounds | null>(null);

  useEffect(() => {
    if (!chatId) return;
    unwrap(api.GET("/v1/tenant/chats/{chat_id}", { params: { path: { chat_id: chatId } } }))
      .then((c) =>
        dispatch({
          type: "load", chatId: c.id,
          // Same schemas; the generator renders tuples differently in nested positions.
          cards: c.cards as unknown as ListingCard[], pins: c.pins as unknown as Pin[],
          chips: c.chips as Chip[], filters: c.filters as unknown as SearchFilters,
          turns: c.messages.map((m): Turn => ({
            role: m.role === "user" ? "user" : "assistant", content: m.content, cardIds: m.card_ids ?? [],
            relaxed: m.relaxed ?? [], claims: (m.claims ?? []) as Turn["claims"],
          })),
        }),
      )
      .catch((e: unknown) => setLoadError(messageFor(e)));
  }, [chatId, dispatch]);

  if (cities.isError) return <ErrorState message={messageFor(cities.error)} />;
  if (loadError) return <ErrorState message={loadError} />;
  if (cities.isPending) return <PageSkeleton />;

  const city = cities.data.find((c) => c.slug === state.filters?.city) ?? cities.data[0];
  const hover = (id: string | null) => dispatch({ type: "hover", id });
  const select = (id: string) => {
    hover(id);
    setMapOpen(false);
    document.getElementById(`card-${id}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
  };

  const map = city && (
    <ListingsMap
      key={city.slug}
      center={city.center}
      zoom={city.default_zoom}
      pins={state.pins}
      activeId={state.hovered}
      onHover={hover}
      onSelect={select}
      fitToPins
      onBoundsChange={(b) => (bounds.current = b)}
      className="h-full min-h-[320px] overflow-hidden rounded-xl border"
    >
      {state.turns.length > 0 && (
        <Button
          size="sm"
          variant="secondary"
          className="absolute left-1/2 top-3 -translate-x-1/2 shadow"
          disabled={state.busy}
          onClick={() => {
            if (!bounds.current) return;
            setMapOpen(false);
            void send({ bbox: bounds.current });
          }}
        >
          <ScanSearch /> Search this area
        </Button>
      )}
    </ListingsMap>
  );

  return (
    <div className="flex h-[calc(100svh-6.5rem)] min-h-[480px] flex-col gap-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 space-y-2">
          <h1 className="text-xl font-semibold tracking-tight">Find a home</h1>
          <FilterChips chips={state.chips} disabled={state.busy} onRemove={(f) => void send({ remove_filters: [f] })} />
        </div>
        <div className="flex shrink-0 gap-2">
          {state.filters && state.chips.length > 0 && (
            <Button variant="outline" size="sm" onClick={() => setSaving(true)}>
              <Bookmark /> Save search
            </Button>
          )}
          <Button variant="outline" size="sm" className="lg:hidden" onClick={() => setMapOpen(true)}>
            <MapIcon /> Map
          </Button>
        </div>
      </div>
      <div className="flex min-h-0 flex-1 gap-4">
        <section className="flex min-h-0 w-full flex-col lg:w-2/5" aria-label="Search chat">
          <ChatPanel state={state} onHover={hover} onSend={(m) => void send({ message: m })} />
        </section>
        <section className="hidden min-h-0 flex-1 lg:block" aria-label="Map">
          {map}
        </section>
      </div>
      <Sheet open={mapOpen} onOpenChange={setMapOpen}>
        <SheetContent side="bottom" className="h-[80svh] p-3">
          <SheetHeader className="p-0">
            <SheetTitle>Map</SheetTitle>
          </SheetHeader>
          {mapOpen && map}
        </SheetContent>
      </Sheet>
      <SaveDialog open={saving} onOpenChange={setSaving} filters={state.filters} defaultName={state.chips.slice(0, 2).map((c) => c.label).join(", ")} />
    </div>
  );
}

function SaveDialog({ open, onOpenChange, filters, defaultName }: {
  open: boolean; onOpenChange: (o: boolean) => void; filters: ReturnType<typeof useSearch>["state"]["filters"];
  defaultName: string;
}) {
  const save = useSaveSearch();
  const [name, setName] = useState("");
  useEffect(() => {
    if (open) setName(defaultName);
  }, [open, defaultName]);
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Save this search</DialogTitle>
        </DialogHeader>
        <form
          id="save-search"
          onSubmit={(e) => {
            e.preventDefault();
            if (!filters || !name.trim()) return;
            save.mutate({ name: name.trim().slice(0, 80), filters }, {
              onSuccess: () => {
                toast.success("Search saved");
                onOpenChange(false);
              },
              onError: (err) => toast.error(messageFor(err)),
            });
          }}
        >
          <Input value={name} onChange={(e) => setName(e.target.value)} aria-label="Name" maxLength={80} autoFocus />
        </form>
        <DialogFooter>
          <Button type="submit" form="save-search" disabled={!name.trim() || save.isPending}>Save</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
