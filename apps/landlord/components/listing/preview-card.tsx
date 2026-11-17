"use client";

import { Badge } from "@rentfit/ui/components/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@rentfit/ui/components/card";
import { cn } from "@rentfit/ui/lib/utils";
import { Check, Circle } from "lucide-react";

import { FIELD_LABELS, inr, type Listing } from "@/lib/listings";

const FURNISHING: Record<string, string> = { unfurnished: "Unfurnished", semi: "Semi-furnished", full: "Fully furnished" };
const TENANTS: Record<string, string> = { any: "Anyone", family: "Families", bachelors: "Bachelors" };

export function PreviewCard({
  listing,
  localityName,
  highlight,
  missing,
}: {
  listing: Listing;
  localityName: string | null;
  highlight: Set<string>;
  missing: string[];
}) {
  const rows: [string, string, string | null][] = [
    ["bhk", "BHK", listing.bhk ? `${listing.bhk} BHK` : null],
    ["rent", "Rent", listing.rent ? `${inr(listing.rent)} / month` : null],
    ["deposit", "Deposit", listing.deposit != null ? inr(listing.deposit) : null],
    ["maintenance", "Maintenance", listing.maintenance != null ? `${inr(listing.maintenance)} / month` : null],
    ["furnishing", "Furnishing", listing.furnishing ? FURNISHING[listing.furnishing] ?? listing.furnishing : null],
    ["tenant_pref", "Tenants", listing.tenant_pref ? TENANTS[listing.tenant_pref] ?? listing.tenant_pref : null],
    ["available_from", "Available from", listing.available_from ? availableLabel(listing.available_from) : null],
    ["sqft", "Area", listing.sqft ? `${listing.sqft} sq ft` : null],
    ["floor", "Floor", listing.floor != null ? `${listing.floor}${listing.total_floors ? ` of ${listing.total_floors}` : ""}` : null],
    ["locality_id", "Area name", localityName],
  ];
  const flags: string[] = [];
  if (listing.no_brokerage) flags.push("No brokerage");
  if (listing.pets) flags.push("Pets allowed");
  if (listing.gated) flags.push("Gated");
  if (listing.parking && listing.parking !== "none") flags.push(`Parking: ${listing.parking}`);

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">{listing.title || "Listing preview"}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4 text-sm">
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5">
          {rows.map(([field, label, value]) => (
            <div key={field} className="contents">
              <dt className="text-muted-foreground">{label}</dt>
              <dd
                data-field={field}
                className={cn("rounded px-1 transition-colors", highlight.has(field) && "bg-yellow-200/70 dark:bg-yellow-500/30")}
              >
                {value ?? <span className="text-muted-foreground">—</span>}
              </dd>
            </div>
          ))}
        </dl>
        {flags.length || listing.amenities?.length ? (
          <div className={cn("flex flex-wrap gap-1.5 rounded", highlight.has("amenities") && "bg-yellow-200/40")}>
            {flags.map((f) => (
              <Badge key={f} variant="secondary">
                {f}
              </Badge>
            ))}
            {listing.amenities?.map((a) => (
              <Badge key={a} variant="outline">
                {a.replace(/_/g, " ")}
              </Badge>
            ))}
          </div>
        ) : null}
        {listing.description ? <p className="whitespace-pre-wrap text-muted-foreground">{listing.description}</p> : null}
        <Checklist missing={missing} photos={listing.photo_count} />
      </CardContent>
    </Card>
  );
}

function Checklist({ missing, photos }: { missing: string[]; photos: number }) {
  const items = [
    ...Object.keys(FIELD_LABELS)
      .filter((f) => f !== "photos")
      .map((f) => ({ key: f, done: !missing.includes(f), label: FIELD_LABELS[f] })),
    { key: "photos", done: photos >= 3, label: `Photos (${photos}/3)` },
  ];
  return (
    <div>
      <h3 className="mb-1.5 text-xs font-medium uppercase tracking-wide text-muted-foreground">Needed to publish</h3>
      <ul className="grid grid-cols-2 gap-1">
        {items.map((i) => (
          <li key={i.key} className={cn("flex items-center gap-1.5", i.done ? "text-muted-foreground" : "font-medium")}>
            {i.done ? <Check className="size-3.5 text-green-600" /> : <Circle className="size-3.5" />}
            {i.label}
          </li>
        ))}
      </ul>
    </div>
  );
}

/** "Now" for today or earlier, else "1 Dec 2026". */
function availableLabel(iso: string): string {
  const d = new Date(`${iso}T00:00:00`);
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return d <= today ? "Now" : d.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
}
