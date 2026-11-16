import type { Listing, Patch } from "./listings";

export type FormValues = {
  bhk: string;
  rent: string;
  deposit: string;
  maintenance: string;
  furnishing: string;
  tenant_pref: string;
  available_from: string;
  sqft: string;
  title: string;
  description: string;
  no_brokerage: boolean;
  pets: boolean;
};

const NUMBERS = ["bhk", "rent", "deposit", "maintenance", "sqft"] as const;
const TEXTS = ["furnishing", "tenant_pref", "available_from", "title", "description"] as const;
const BOOLS = ["no_brokerage", "pets"] as const;

export function formFromListing(l: Listing): FormValues {
  const s = (v: unknown) => (v == null ? "" : String(v));
  return {
    bhk: s(l.bhk), rent: s(l.rent), deposit: s(l.deposit), maintenance: s(l.maintenance), furnishing: s(l.furnishing),
    tenant_pref: s(l.tenant_pref), available_from: s(l.available_from), sqft: s(l.sqft), title: s(l.title),
    description: s(l.description), no_brokerage: Boolean(l.no_brokerage), pets: Boolean(l.pets),
  };
}

/** The minimal patch list from the listing to the form values (unchanged fields send nothing). */
export function diffFormToPatches(l: Listing, f: FormValues): Patch[] {
  const out: Patch[] = [];
  for (const k of NUMBERS) {
    const raw = f[k].replace(/[,\s₹]/g, "");
    const v = raw === "" ? null : Number(raw);
    if (v !== (l[k] ?? null)) out.push({ op: "set", field: k, value: v });
  }
  for (const k of TEXTS) {
    const v = f[k].trim() === "" ? null : f[k].trim();
    if (v !== (l[k] ?? null)) out.push({ op: "set", field: k, value: v });
  }
  for (const k of BOOLS) {
    if (f[k] !== Boolean(l[k])) out.push({ op: "set", field: k, value: f[k] });
  }
  return out;
}
