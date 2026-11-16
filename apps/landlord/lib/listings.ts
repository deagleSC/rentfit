import { qk, unwrap, type components } from "@rentfit/api-client";
import { PHOTO_MAX_BYTES, resizeToWebp } from "@rentfit/ui/lib/image";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "./api";

export type Listing = components["schemas"]["Listing"];
export type Change = components["schemas"]["Change"];
export type Photo = components["schemas"]["Photo"];
export type ChatHistory = components["schemas"]["ChatHistory"];
export type TurnResult = components["schemas"]["TurnResult"];
export type RentSuggestion = components["schemas"]["RentSuggestion"];
export type Patch = components["schemas"]["SetField"] | components["schemas"]["AddAmenity"] | components["schemas"]["RemoveAmenity"];

export const lk = {
  all: () => ["listings"] as const,
  one: (id: string) => ["listings", id] as const,
  chat: (id: string) => ["listings", id, "chat"] as const,
  photos: (id: string) => ["listings", id, "photos"] as const,
  rent: (id: string) => ["listings", id, "rent"] as const,
};

export function useListings() {
  return useQuery({ queryKey: lk.all(), queryFn: () => unwrap(api.GET("/v1/landlord/listings")) });
}

export function useListing(id: string) {
  return useQuery({
    queryKey: lk.one(id),
    queryFn: () => unwrap(api.GET("/v1/landlord/listings/{listing_id}", { params: { path: { listing_id: id } } })),
  });
}

export function useCreateListing() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => unwrap(api.POST("/v1/landlord/listings", { body: {} })),
    onSuccess: () => qc.invalidateQueries({ queryKey: lk.all() }),
  });
}

/** Refresh everything derived from the listing after a change. */
function useListingRefresh(id: string) {
  const qc = useQueryClient();
  return (listing?: Listing) => {
    if (listing) qc.setQueryData(lk.one(id), listing);
    void qc.invalidateQueries({ queryKey: lk.rent(id) });
    void qc.invalidateQueries({ queryKey: lk.chat(id) });
    void qc.invalidateQueries({ queryKey: lk.all() });
  };
}

export function usePatchListing(id: string) {
  const refresh = useListingRefresh(id);
  return useMutation({
    mutationFn: ({ version, patches }: { version: number; patches: Patch[] }) =>
      unwrap(
        api.PATCH("/v1/landlord/listings/{listing_id}", {
          params: { path: { listing_id: id }, header: { "if-match": String(version) } },
          headers: { "If-Match": String(version) },
          body: patches,
        }),
      ),
    onSuccess: (r) => refresh(r.listing),
  });
}

export function useChat(id: string) {
  return useQuery({
    queryKey: lk.chat(id),
    queryFn: () => unwrap(api.GET("/v1/landlord/listings/{listing_id}/chat", { params: { path: { listing_id: id } } })),
  });
}

export function useSendChat(id: string) {
  const qc = useQueryClient();
  const refresh = useListingRefresh(id);
  return useMutation({
    mutationFn: (message: string) =>
      unwrap(api.POST("/v1/landlord/listings/{listing_id}/chat", { params: { path: { listing_id: id } }, body: { message } })),
    onSuccess: (r) => {
      refresh(r.listing);
      qc.setQueryData(lk.chat(id), (old: ChatHistory | undefined) =>
        old ? { ...old, messages: r.messages, missing: r.missing, next: r.next ?? null } : old,
      );
    },
  });
}

export function useSetLocation(id: string) {
  const refresh = useListingRefresh(id);
  return useMutation({
    mutationFn: (p: { lat: number; lng: number }) =>
      unwrap(api.PUT("/v1/landlord/listings/{listing_id}/location", { params: { path: { listing_id: id } }, body: p })),
    onSuccess: (r) => refresh(r.listing),
  });
}

export type Action = "publish" | "pause" | "resume" | "let";

export function useTransition(id: string) {
  const refresh = useListingRefresh(id);
  return useMutation({
    mutationFn: (action: Action) =>
      unwrap(api.POST(`/v1/landlord/listings/{listing_id}/${action}`, { params: { path: { listing_id: id } } })),
    onSuccess: (l) => refresh(l),
  });
}

export function useRentSuggestion(id: string, enabled: boolean) {
  return useQuery({
    queryKey: lk.rent(id),
    enabled,
    queryFn: () =>
      unwrap(api.GET("/v1/landlord/listings/{listing_id}/rent-suggestion", { params: { path: { listing_id: id } } })),
  });
}

export function usePhotos(id: string) {
  return useQuery({
    queryKey: lk.photos(id),
    queryFn: () => unwrap(api.GET("/v1/landlord/listings/{listing_id}/photos", { params: { path: { listing_id: id } } })),
    staleTime: 30 * 60 * 1000, // signed URLs last an hour
  });
}

async function put(url: string, blob: Blob): Promise<void> {
  const res = await fetch(url, { method: "PUT", body: blob, headers: { "Content-Type": blob.type } });
  if (!res.ok) throw new Error(`Upload failed (${res.status})`);
}

/** Resize in the browser, upload full + thumbnail to signed URLs, then confirm. */
export async function uploadPhoto(id: string, file: File): Promise<Photo[]> {
  const full = await resizeToWebp(file, 1600);
  const thumb = await resizeToWebp(file, 480, 0.75);
  if (!full || !thumb) throw new Error(`${file.name}: this browser can't read that image. Try a JPEG or PNG.`);
  if (full.size > PHOTO_MAX_BYTES) throw new Error(`${file.name} is still over 5 MB after resizing.`);
  const start = await unwrap(
    api.POST("/v1/landlord/listings/{listing_id}/photos", {
      params: { path: { listing_id: id } },
      body: { content_type: "image/webp", bytes: full.size, thumb_bytes: thumb.size },
    }),
  );
  await put(start.upload_url, full);
  await put(start.thumb_upload_url, thumb);
  return unwrap(
    api.POST("/v1/landlord/listings/{listing_id}/photos/{photo_id}/confirm", {
      params: { path: { listing_id: id, photo_id: start.photo_id } },
    }),
  );
}

export function useDeletePhoto(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (photoId: string) =>
      unwrap(api.DELETE("/v1/landlord/listings/{listing_id}/photos/{photo_id}", {
        params: { path: { listing_id: id, photo_id: photoId } },
      })),
    onSuccess: (photos) => {
      qc.setQueryData(lk.photos(id), photos);
      void qc.invalidateQueries({ queryKey: lk.one(id) });
    },
  });
}

export const FIELD_LABELS: Record<string, string> = {
  city: "City", locality_id: "Area", location: "Map pin", bhk: "BHK", rent: "Rent", deposit: "Deposit",
  furnishing: "Furnishing", tenant_pref: "Tenants", available_from: "Available from", photos: "Photos",
};

export function inr(v: number | null | undefined): string {
  return v == null ? "—" : `₹${v.toLocaleString("en-IN")}`;
}

export { qk };
