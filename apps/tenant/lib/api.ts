import { createApiClient, ensureProfile, profileFromMetadata, qk, unwrap } from "@rentfit/api-client";
import { useQuery } from "@tanstack/react-query";

import { env } from "./env";
import { supabase } from "./supabase";

export const api = createApiClient({
  baseUrl: env.apiUrl,
  getToken: async () => (await supabase().auth.getSession()).data.session?.access_token ?? null,
  onWrongApp: () => window.location.assign(env.otherAppUrl),
  onUnauthenticated: () => window.location.assign(`/sign-in?next=${encodeURIComponent(window.location.pathname)}`),
});

export async function signUpDetails() {
  const { data } = await supabase().auth.getUser();
  return profileFromMetadata(data.user?.user_metadata);
}

export function useMe() {
  return useQuery({ queryKey: qk.me(), queryFn: () => ensureProfile(api, signUpDetails), retry: false });
}

export function useCities() {
  return useQuery({
    queryKey: qk.cities(),
    queryFn: () => unwrap(api.GET("/v1/cities")),
    staleTime: 60 * 60 * 1000,
  });
}

export function useMapPins(city: string | undefined) {
  return useQuery({
    queryKey: ["map-pins", city],
    queryFn: () => unwrap(api.GET("/v1/tenant/map/listings", { params: { query: { city: city ?? "" } } })),
    enabled: !!city,
    staleTime: 60 * 1000,
  });
}
