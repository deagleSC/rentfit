"use client";

import { messageFor } from "@rentfit/api-client";
import { Button } from "@rentfit/ui/components/button";
import { Card, CardContent, CardHeader, CardTitle } from "@rentfit/ui/components/card";
import { PHOTO_TYPES } from "@rentfit/ui/lib/image";
import { useQueryClient } from "@tanstack/react-query";
import { ImagePlus, Loader2, Trash2 } from "lucide-react";
import { useRef, useState, type ChangeEvent } from "react";
import { toast } from "sonner";

import { lk, uploadPhoto, useDeletePhoto, usePhotos, type Listing } from "@/lib/listings";

const RAW_MAX = 25 * 1024 * 1024; // before resizing; the uploaded WebP must be under 5 MB

export function PhotosPanel({ listing }: { listing: Listing }) {
  const photos = usePhotos(listing.id);
  const del = useDeletePhoto(listing.id);
  const qc = useQueryClient();
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(0);

  async function onFiles(e: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(e.target.files ?? []);
    e.target.value = "";
    const room = 15 - (photos.data?.length ?? 0);
    if (files.length > room) toast.warning(`Only ${room} more photo${room === 1 ? "" : "s"} can be added.`);
    for (const f of files.slice(0, Math.max(0, room))) {
      if (!PHOTO_TYPES.includes(f.type) && !/\.(heic|heif)$/i.test(f.name)) {
        toast.error(`${f.name} is not a JPEG, PNG, WebP or HEIC image.`);
        continue;
      }
      if (f.size > RAW_MAX) {
        toast.error(`${f.name} is too large.`);
        continue;
      }
      setBusy((n) => n + 1);
      try {
        const list = await uploadPhoto(listing.id, f);
        qc.setQueryData(lk.photos(listing.id), list);
        void qc.invalidateQueries({ queryKey: lk.one(listing.id) });
        void qc.invalidateQueries({ queryKey: lk.chat(listing.id) });
      } catch (err) {
        toast.error(err instanceof Error ? err.message : messageFor(err));
      } finally {
        setBusy((n) => n - 1);
      }
    }
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="text-base">Photos</CardTitle>
        <Button size="sm" variant="outline" onClick={() => input.current?.click()} disabled={busy > 0 || listing.status === "let"}>
          {busy > 0 ? <Loader2 className="animate-spin" /> : <ImagePlus />}
          Add photos
        </Button>
        <input ref={input} type="file" accept="image/*,.heic,.heif" multiple hidden onChange={onFiles} aria-label="Choose photos" />
      </CardHeader>
      <CardContent>
        {photos.data?.length ? (
          <ul className="grid grid-cols-3 gap-2">
            {photos.data.map((p, i) => (
              <li key={p.id} className="group relative aspect-[4/3] overflow-hidden rounded-lg border bg-muted">
                {/* eslint-disable-next-line @next/next/no-img-element -- signed URLs, not optimisable */}
                <img src={p.thumb_url} alt={`Photo ${i + 1}`} className="size-full object-cover" />
                <button
                  type="button"
                  aria-label={`Delete photo ${i + 1}`}
                  className="absolute right-1 top-1 rounded-md bg-background/80 p-1 opacity-0 transition-opacity group-hover:opacity-100 focus:opacity-100"
                  onClick={() => del.mutate(p.id, { onError: (e) => toast.error(messageFor(e)) })}
                >
                  <Trash2 className="size-4" />
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted-foreground">Add at least 3 photos. They're resized in your browser before upload.</p>
        )}
      </CardContent>
    </Card>
  );
}
