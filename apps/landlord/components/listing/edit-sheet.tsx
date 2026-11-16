"use client";

import { ApiError, messageFor } from "@rentfit/api-client";
import { Button } from "@rentfit/ui/components/button";
import { Checkbox } from "@rentfit/ui/components/checkbox";
import { Field, FieldGroup, FieldLabel } from "@rentfit/ui/components/field";
import { Input } from "@rentfit/ui/components/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@rentfit/ui/components/select";
import { Sheet, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle, SheetTrigger } from "@rentfit/ui/components/sheet";
import { Textarea } from "@rentfit/ui/components/textarea";
import { useQueryClient } from "@tanstack/react-query";
import { Pencil } from "lucide-react";
import { useState, type FormEvent } from "react";
import { toast } from "sonner";

import { diffFormToPatches, formFromListing, type FormValues } from "@/lib/form-diff";
import { lk, usePatchListing, type Change, type Listing } from "@/lib/listings";

export function EditSheet({ listing, onChanges }: { listing: Listing; onChanges: (c: Change[]) => void }) {
  const [open, setOpen] = useState(false);
  const [f, setF] = useState<FormValues>(() => formFromListing(listing));
  const patch = usePatchListing(listing.id);
  const qc = useQueryClient();
  const set = <K extends keyof FormValues>(k: K, v: FormValues[K]) => setF((s) => ({ ...s, [k]: v }));

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    const patches = diffFormToPatches(listing, f);
    if (!patches.length) return setOpen(false);
    patch.mutate(
      { version: listing.version, patches },
      {
        onSuccess: (r) => {
          onChanges(r.changes);
          toast.success("Saved");
          setOpen(false);
        },
        onError: (err) => {
          if (err instanceof ApiError && err.code === "version_conflict") {
            toast.error("This listing changed (maybe from the chat). Reloaded the latest; check your edits.");
            void qc.invalidateQueries({ queryKey: lk.one(listing.id) });
          } else toast.error(messageFor(err));
        },
      },
    );
  }

  const num = (k: "bhk" | "rent" | "deposit" | "maintenance" | "sqft", label: string) => (
    <Field>
      <FieldLabel htmlFor={`f-${k}`}>{label}</FieldLabel>
      <Input id={`f-${k}`} inputMode="numeric" value={f[k]} onChange={(e) => set(k, e.target.value)} />
    </Field>
  );

  return (
    <Sheet open={open} onOpenChange={(o) => { setOpen(o); if (o) setF(formFromListing(listing)); }}>
      <SheetTrigger asChild>
        <Button variant="outline" disabled={listing.status === "let"}>
          <Pencil />
          Edit details
        </Button>
      </SheetTrigger>
      <SheetContent className="overflow-y-auto">
        <form onSubmit={onSubmit} className="flex h-full flex-col">
          <SheetHeader>
            <SheetTitle>Edit details</SheetTitle>
            <SheetDescription>Same changes as in chat, by hand.</SheetDescription>
          </SheetHeader>
          <FieldGroup className="flex-1 px-4">
            <div className="grid grid-cols-2 gap-3">
              {num("bhk", "BHK")}
              {num("sqft", "Area (sq ft)")}
              {num("rent", "Rent (₹/month)")}
              {num("deposit", "Deposit (₹)")}
              {num("maintenance", "Maintenance (₹/month)")}
              <Field>
                <FieldLabel htmlFor="f-available">Available from</FieldLabel>
                <Input id="f-available" type="date" value={f.available_from} onChange={(e) => set("available_from", e.target.value)} />
              </Field>
            </div>
            <Field>
              <FieldLabel htmlFor="f-furnishing">Furnishing</FieldLabel>
              <Select value={f.furnishing || undefined} onValueChange={(v) => set("furnishing", v)}>
                <SelectTrigger id="f-furnishing"><SelectValue placeholder="Choose" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="unfurnished">Unfurnished</SelectItem>
                  <SelectItem value="semi">Semi-furnished</SelectItem>
                  <SelectItem value="full">Fully furnished</SelectItem>
                </SelectContent>
              </Select>
            </Field>
            <Field>
              <FieldLabel htmlFor="f-tenants">Tenants</FieldLabel>
              <Select value={f.tenant_pref || undefined} onValueChange={(v) => set("tenant_pref", v)}>
                <SelectTrigger id="f-tenants"><SelectValue placeholder="Choose" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="any">Anyone</SelectItem>
                  <SelectItem value="family">Families</SelectItem>
                  <SelectItem value="bachelors">Bachelors</SelectItem>
                </SelectContent>
              </Select>
            </Field>
            <Field>
              <FieldLabel htmlFor="f-title">Title</FieldLabel>
              <Input id="f-title" maxLength={120} value={f.title} onChange={(e) => set("title", e.target.value)} />
            </Field>
            <Field>
              <FieldLabel htmlFor="f-description">Description</FieldLabel>
              <Textarea id="f-description" rows={4} maxLength={4000} value={f.description} onChange={(e) => set("description", e.target.value)} />
            </Field>
            <Field orientation="horizontal">
              <Checkbox id="f-nobroker" checked={f.no_brokerage} onCheckedChange={(v) => set("no_brokerage", v === true)} />
              <FieldLabel htmlFor="f-nobroker" className="font-normal">No brokerage</FieldLabel>
            </Field>
            <Field orientation="horizontal">
              <Checkbox id="f-pets" checked={f.pets} onCheckedChange={(v) => set("pets", v === true)} />
              <FieldLabel htmlFor="f-pets" className="font-normal">Pets allowed</FieldLabel>
            </Field>
          </FieldGroup>
          <SheetFooter>
            <Button type="submit" disabled={patch.isPending}>Save</Button>
          </SheetFooter>
        </form>
      </SheetContent>
    </Sheet>
  );
}
