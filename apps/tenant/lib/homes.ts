"use client";

import { qk, unwrap, type components } from "@rentfit/api-client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "./api";
import type { ListingCard, SearchFilters } from "./search";

/** What `unwrap` returns (openapi-fetch widens tuples, so the schema type does not match exactly). */
export type ListingDetail = NonNullable<ReturnType<typeof useListingDetail>["data"]>;
export type SavedSearch = components["schemas"]["SavedSearch"];
export type EnquirySummary = components["schemas"]["EnquirySummary"];
export type EnquiryThread = components["schemas"]["EnquiryThread"];

export function useListingDetail(id: string, poiId?: string) {
  return useQuery({
    queryKey: qk.listing(id, poiId),
    queryFn: () =>
      unwrap(api.GET("/v1/listings/{listing_id}", { params: { path: { listing_id: id }, query: { poi_id: poiId } } })),
  });
}

export function useShortlist() {
  return useQuery({ queryKey: qk.shortlist(), queryFn: () => unwrap(api.GET("/v1/tenant/shortlists")) });
}

/** Add or remove a home from the shortlist; updates cards and detail views optimistically. */
export function useToggleShortlist() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, on }: { id: string; on: boolean }) => {
      const opts = { params: { path: { listing_id: id } } };
      const { response } = on
        ? await api.PUT("/v1/tenant/shortlists/{listing_id}", opts)
        : await api.DELETE("/v1/tenant/shortlists/{listing_id}", opts);
      if (!response.ok) throw new Error("Could not update the shortlist.");
    },
    onSettled: (_d, _e, { id }) => {
      void qc.invalidateQueries({ queryKey: qk.shortlist() });
      void qc.invalidateQueries({ queryKey: ["listing", id] });
    },
  });
}

export function useSavedSearches() {
  return useQuery({ queryKey: qk.saved(), queryFn: () => unwrap(api.GET("/v1/tenant/saved-searches")) });
}

export function useSaveSearch() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { name: string; filters: SearchFilters }) =>
      unwrap(api.POST("/v1/tenant/saved-searches", { body })),
    onSuccess: () => void qc.invalidateQueries({ queryKey: qk.saved() }),
  });
}

export function useDeleteSaved() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => {
      await api.DELETE("/v1/tenant/saved-searches/{saved_id}", { params: { path: { saved_id: id } } });
    },
    onSuccess: () => void qc.invalidateQueries({ queryKey: qk.saved() }),
  });
}

export function useChats() {
  return useQuery({ queryKey: qk.chats(), queryFn: () => unwrap(api.GET("/v1/tenant/chats")) });
}

export function useEnquiries() {
  return useQuery({
    queryKey: qk.enquiries("tenant"),
    queryFn: () => unwrap(api.GET("/v1/tenant/enquiries")),
    refetchInterval: 30_000,
  });
}

export function useEnquiry(id: string | null) {
  return useQuery({
    queryKey: qk.enquiry(id ?? ""),
    queryFn: () => unwrap(api.GET("/v1/enquiries/{enquiry_id}", { params: { path: { enquiry_id: id ?? "" } } })),
    enabled: !!id,
    refetchInterval: 15_000,
  });
}

export function useStartEnquiry() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { listing_id: string; message: string }) => unwrap(api.POST("/v1/tenant/enquiries", { body })),
    onSuccess: (t) => {
      qc.setQueryData(qk.enquiry(t.enquiry.id), t);
      void qc.invalidateQueries({ queryKey: qk.enquiries("tenant") });
      void qc.invalidateQueries({ queryKey: ["listing", t.enquiry.listing_id] });
    },
  });
}

export function useReply(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: string) =>
      unwrap(api.POST("/v1/enquiries/{enquiry_id}/messages", { params: { path: { enquiry_id: id } }, body: { body } })),
    onSuccess: (t) => {
      qc.setQueryData(qk.enquiry(id), t);
      void qc.invalidateQueries({ queryKey: qk.enquiries("tenant") });
    },
  });
}

export function useUnread() {
  return useQuery({
    queryKey: qk.notifications(),
    queryFn: () => unwrap(api.GET("/v1/notifications")),
    refetchInterval: 30_000,
    select: (n) => n.filter((x) => !x.read).length,
  });
}

export function inr(v: number | null | undefined): string {
  return v == null ? "—" : `₹${v.toLocaleString("en-IN")}`;
}

export function shortInr(v: number): string {
  return v >= 100_000 ? `₹${+(v / 100_000).toFixed(1)}L` : `₹${Math.round(v / 1000)}k`;
}

export const FURNISHING: Record<string, string> = { unfurnished: "Unfurnished", semi: "Semi-furnished", full: "Furnished" };
export type { ListingCard };
