import { describe, expect, it } from "vitest";

import { diffFormToPatches, formFromListing } from "./form-diff";
import type { Listing } from "./listings";

const listing = {
  id: "l1", landlord_id: "u1", status: "draft", version: 3, photo_count: 0, flags: {}, amenities: [],
  bhk: 2, rent: 35000, deposit: 70000, maintenance: null, furnishing: "semi", tenant_pref: "family",
  available_from: "2026-12-01", sqft: null, title: null, description: null, no_brokerage: null, pets: null,
} as unknown as Listing;

describe("diffFormToPatches", () => {
  it("sends nothing when nothing changed", () => {
    expect(diffFormToPatches(listing, formFromListing(listing))).toEqual([]);
  });

  it("sends only the changed fields, with numbers parsed", () => {
    const f = { ...formFromListing(listing), deposit: "1,05,000", tenant_pref: "any", no_brokerage: true };
    expect(diffFormToPatches(listing, f)).toEqual([
      { op: "set", field: "deposit", value: 105000 },
      { op: "set", field: "tenant_pref", value: "any" },
      { op: "set", field: "no_brokerage", value: true },
    ]);
  });

  it("clears a field emptied in the form", () => {
    const f = { ...formFromListing(listing), rent: "" };
    expect(diffFormToPatches(listing, f)).toEqual([{ op: "set", field: "rent", value: null }]);
  });
});
