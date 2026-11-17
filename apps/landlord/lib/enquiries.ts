"use client";

import { qk, unwrap } from "@rentfit/api-client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "./api";

export function useEnquiries() {
  return useQuery({
    queryKey: qk.enquiries("landlord"),
    queryFn: () => unwrap(api.GET("/v1/landlord/enquiries")),
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

export function useReply(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: string) =>
      unwrap(api.POST("/v1/enquiries/{enquiry_id}/messages", { params: { path: { enquiry_id: id } }, body: { body } })),
    onSuccess: (t) => {
      qc.setQueryData(qk.enquiry(id), t);
      void qc.invalidateQueries({ queryKey: qk.enquiries("landlord") });
    },
  });
}
