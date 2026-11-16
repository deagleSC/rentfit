"use client";

import { messageFor } from "@rentfit/api-client";
import { Alert, AlertDescription, AlertTitle } from "@rentfit/ui/components/alert";
import { Button } from "@rentfit/ui/components/button";
import { Card, CardContent, CardHeader, CardTitle } from "@rentfit/ui/components/card";
import dynamic from "next/dynamic";
import { toast } from "sonner";

import { useCities } from "@/lib/api";
import { usePatchListing, useSetLocation, type Listing } from "@/lib/listings";

const PinPicker = dynamic(() => import("@rentfit/ui/map/pin-picker").then((m) => m.PinPicker), { ssr: false });

export function PinPanel({ listing, localityName }: { listing: Listing; localityName: string | null }) {
  const cities = useCities();
  const setLocation = useSetLocation(listing.id);
  const patch = usePatchListing(listing.id);
  const city = cities.data?.find((c) => c.slug === (listing.city ?? "bangalore")) ?? cities.data?.[0];
  const mismatch = (listing.flags as { locality_mismatch?: { pin: string; pin_name: string } }).locality_mismatch;

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">Location</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <p className="text-muted-foreground">Click the map to drop a pin, or drag it to adjust.</p>
        {city ? (
          <PinPicker
            value={listing.location ?? null}
            center={[city.center[0] as number, city.center[1] as number]}
            onChange={(p) =>
              setLocation.mutate(p, {
                onSuccess: (r) => toast.success(r.mismatch ? `Pin is in ${r.locality_name}` : `Pinned in ${r.locality_name}`),
                onError: (e) => toast.error(messageFor(e)),
              })
            }
          />
        ) : null}
        {mismatch ? (
          <Alert>
            <AlertTitle>Which area is right?</AlertTitle>
            <AlertDescription className="space-y-2">
              <p>
                You said {localityName ?? "another area"}, but the pin is in {mismatch.pin_name}.
              </p>
              <Button
                size="sm"
                variant="outline"
                disabled={patch.isPending}
                onClick={() =>
                  patch.mutate(
                    { version: listing.version, patches: [{ op: "set", field: "locality_id", value: mismatch.pin }] },
                    { onError: (e) => toast.error(messageFor(e)) },
                  )
                }
              >
                Use {mismatch.pin_name}
              </Button>
            </AlertDescription>
          </Alert>
        ) : null}
      </CardContent>
    </Card>
  );
}
