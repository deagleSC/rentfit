"use client";

import { messageFor } from "@rentfit/api-client";
import { PageHeader } from "@rentfit/ui/blocks/dashboard-layout";
import { ErrorState, PageSkeleton } from "@rentfit/ui/blocks/states";
import { Badge } from "@rentfit/ui/components/badge";
import { Button } from "@rentfit/ui/components/button";
import { Card, CardContent, CardHeader, CardTitle } from "@rentfit/ui/components/card";
import { Textarea } from "@rentfit/ui/components/textarea";
import { cn } from "@rentfit/ui/lib/utils";
import { Heart, MessageSquare, Route } from "lucide-react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { use, useState } from "react";
import { toast } from "sonner";

import { FURNISHING, inr, useListingDetail, useStartEnquiry, useToggleShortlist, type ListingDetail } from "@/lib/homes";

const KIND: Record<string, string> = {
  metro_station: "Metro", rail_station: "Railway", tech_park: "Office hub", hospital: "Hospital",
};
const TENANTS: Record<string, string> = { any: "Families and bachelors", family: "Families", bachelors: "Bachelors" };

function distance(m: number) {
  return m < 1000 ? `${m} m` : `${(m / 1000).toFixed(1)} km`;
}

const NearbyMapLazy = dynamic(() => import("@/components/nearby-map").then((m) => m.NearbyMap), { ssr: false });

function Enquire({ d }: { d: ListingDetail }) {
  const start = useStartEnquiry();
  const [text, setText] = useState("Hi, is this flat still available? I'd like to visit.");
  if (d.enquiry_id) {
    return (
      <Button asChild variant="outline" className="w-full">
        <Link href={`/enquiries?id=${d.enquiry_id}`}><MessageSquare /> Open your enquiry</Link>
      </Button>
    );
  }
  return (
    <form
      className="space-y-2"
      onSubmit={(e) => {
        e.preventDefault();
        start.mutate({ listing_id: d.id, message: text }, {
          onSuccess: () => toast.success("Enquiry sent to the landlord"),
          onError: (err) => toast.error(messageFor(err)),
        });
      }}
    >
      <Textarea value={text} onChange={(e) => setText(e.target.value)} rows={3} maxLength={2000} aria-label="Message to the landlord" />
      <p className="text-xs text-muted-foreground">Phone numbers and emails are removed; chat here until you're ready to visit.</p>
      <Button type="submit" className="w-full" disabled={!text.trim() || start.isPending}>
        <MessageSquare /> Send enquiry
      </Button>
    </form>
  );
}

export default function ListingPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [poi, setPoi] = useState<string>();
  const q = useListingDetail(id, poi);
  const toggle = useToggleShortlist();
  const [photo, setPhoto] = useState(0);

  if (q.isError) return <ErrorState message={messageFor(q.error)} />;
  if (q.isPending) return <PageSkeleton />;
  const d = q.data;
  const facts: [string, string][] = [
    ["Rent", `${inr(d.rent)} / month`], ["Deposit", inr(d.deposit)],
    ...(d.maintenance ? ([["Maintenance", `${inr(d.maintenance)} / month`]] as [string, string][]) : []),
    ["Furnishing", FURNISHING[d.furnishing] ?? d.furnishing], ["For", TENANTS[d.tenant_pref] ?? d.tenant_pref],
    ...(d.sqft ? ([["Area", `${d.sqft} sq ft`]] as [string, string][]) : []),
    ...(d.floor != null ? ([["Floor", d.total_floors ? `${d.floor} of ${d.total_floors}` : String(d.floor)]] as [string, string][]) : []),
    ["Available", d.available_from ? new Date(d.available_from).toLocaleDateString("en-IN", { day: "numeric", month: "short" }) : "Now"],
  ];
  const flags = [d.pets && "Pets OK", d.gated && "Gated society", d.no_brokerage && "No brokerage",
                 d.parking && d.parking !== "none" && `Parking: ${d.parking}`].filter(Boolean) as string[];

  return (
    <>
      <PageHeader
        title={d.title || `${d.bhk} BHK in ${d.locality}`}
        description={`${d.locality}, ${d.city === "bangalore" ? "Bengaluru" : "Mumbai"}`}
        back={{ href: "/", label: "Search" }}
        actions={
          <Button variant="outline" onClick={() => toggle.mutate({ id: d.id, on: !d.shortlisted })} aria-pressed={d.shortlisted}>
            <Heart className={cn(d.shortlisted && "fill-primary text-primary")} />
            {d.shortlisted ? "Shortlisted" : "Shortlist"}
          </Button>
        }
      />
      <div className="grid gap-6 lg:grid-cols-[1fr_340px]">
        <div className="space-y-6">
          {d.photos.length > 0 && (
            <div className="space-y-2">
              {/* eslint-disable-next-line @next/next/no-img-element -- signed storage URLs */}
              <img src={d.photos[photo]?.url} alt={`Photo ${photo + 1} of ${d.photos.length}`} className="aspect-[4/3] w-full rounded-xl border object-cover" />
              <div className="flex gap-2 overflow-x-auto">
                {d.photos.map((p, i) => (
                  <button key={p.thumb_url} type="button" onClick={() => setPhoto(i)} aria-label={`Show photo ${i + 1}`}
                          className={cn("size-16 shrink-0 overflow-hidden rounded-md border-2", i === photo ? "border-primary" : "border-transparent")}>
                    {/* eslint-disable-next-line @next/next/no-img-element -- signed storage URLs */}
                    <img src={p.thumb_url} alt="" className="size-full object-cover" />
                  </button>
                ))}
              </div>
            </div>
          )}
          <Card>
            <CardHeader><CardTitle>Details</CardTitle></CardHeader>
            <CardContent className="space-y-4">
              <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm sm:grid-cols-3">
                {facts.map(([k, v]) => (
                  <div key={k}><dt className="text-muted-foreground">{k}</dt><dd className="font-medium tabular-nums">{v}</dd></div>
                ))}
              </dl>
              {(flags.length > 0 || d.amenities.length > 0) && (
                <div className="flex flex-wrap gap-1.5">
                  {flags.map((f) => <Badge key={f}>{f}</Badge>)}
                  {d.amenities.map((a) => <Badge key={a} variant="secondary">{a.replace(/_/g, " ")}</Badge>)}
                </div>
              )}
              {d.description && <p className="whitespace-pre-line text-sm leading-relaxed">{d.description}</p>}
            </CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle>About {d.locality}</CardTitle></CardHeader>
            <CardContent className="space-y-3 text-sm">
              {d.notes.map((n) => <p key={n.chunk_id} className="leading-relaxed">{n.text}</p>)}
              <p className="text-xs text-muted-foreground">Source: © OpenStreetMap contributors</p>
            </CardContent>
          </Card>
        </div>
        <div className="space-y-6">
          <Card>
            <CardHeader><CardTitle>Contact the landlord</CardTitle></CardHeader>
            <CardContent><Enquire d={d} /></CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle>Nearby</CardTitle></CardHeader>
            <CardContent className="space-y-3">
              <NearbyMapLazy d={d} />
              <ul className="space-y-1 text-sm">
                {d.nearby.map((p) => (
                  <li key={p.id} className="flex items-center justify-between gap-2">
                    <span className="min-w-0 truncate"><span className="text-muted-foreground">{KIND[p.kind]}:</span> {p.name}</span>
                    <span className="flex shrink-0 items-center gap-1 tabular-nums text-muted-foreground">
                      {distance(p.metres)}
                      <Button variant="ghost" size="icon" className="size-7" aria-label={`Commute to ${p.name}`} onClick={() => setPoi(p.id)}>
                        <Route className="size-3.5" />
                      </Button>
                    </span>
                  </li>
                ))}
              </ul>
              {d.commute && (
                <p className="rounded-lg bg-muted p-2.5 text-sm" data-testid="commute">
                  About <b>{d.commute.minutes} min</b> by car to {d.commute.to}
                  {d.commute.provider === "haversine" && " (estimate from distance)"}.
                </p>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </>
  );
}
