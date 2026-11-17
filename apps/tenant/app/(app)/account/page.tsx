"use client";

import { messageFor, qk, unwrap } from "@rentfit/api-client";
import { PageHeader } from "@rentfit/ui/blocks/dashboard-layout";
import { ErrorState, PageSkeleton } from "@rentfit/ui/blocks/states";
import { Button } from "@rentfit/ui/components/button";
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@rentfit/ui/components/card";
import { Field, FieldDescription, FieldGroup, FieldLabel } from "@rentfit/ui/components/field";
import { Input } from "@rentfit/ui/components/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@rentfit/ui/components/select";
import { Spinner } from "@rentfit/ui/components/spinner";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { toast } from "sonner";

import { api, useCities, useMe } from "@/lib/api";

/** Profile: name and home city (where a search starts when you don't name a city). */
export default function AccountPage() {
  const me = useMe();
  const cities = useCities();
  const queryClient = useQueryClient();
  const [city, setCity] = useState<string | undefined>();

  const save = useMutation({
    mutationFn: (body: { name?: string; city?: string | null }) =>
      unwrap(api.PATCH("/v1/me", { body })),
    onSuccess: (data) => {
      queryClient.setQueryData(qk.me(), data);
      toast.success("Saved");
    },
  });

  if (me.isError) return <ErrorState message={messageFor(me.error)} />;
  if (cities.isError) return <ErrorState message={messageFor(cities.error)} />;
  if (me.isPending || cities.isPending) return <PageSkeleton />;

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    save.mutate({
      name: String(form.get("name") ?? "").trim(),
      ...(city !== undefined ? { city } : {}),
    });
  }

  return (
    <>
      <PageHeader title="Account" description="Your name and the city your searches start in." />
      <Card className="max-w-xl">
        <form onSubmit={onSubmit}>
          <CardHeader>
            <CardTitle className="text-base">Profile</CardTitle>
          </CardHeader>
          <CardContent>
            <FieldGroup>
              <Field>
                <FieldLabel htmlFor="name">Name</FieldLabel>
                <Input id="name" name="name" defaultValue={me.data.name} required maxLength={200} />
              </Field>
              <Field>
                <FieldLabel htmlFor="city">Home city</FieldLabel>
                <Select defaultValue={me.data.city ?? undefined} onValueChange={setCity}>
                  <SelectTrigger id="city" className="sm:max-w-64">
                    <SelectValue placeholder="Choose a city" />
                  </SelectTrigger>
                  <SelectContent>
                    {cities.data.map((c) => (
                      <SelectItem key={c.slug} value={c.slug}>
                        {c.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <FieldDescription>Used when a search doesn't name a city.</FieldDescription>
              </Field>
              {save.isError ? <p className="text-sm text-destructive">{messageFor(save.error)}</p> : null}
            </FieldGroup>
          </CardContent>
          <CardFooter className="mt-6">
            <Button type="submit" disabled={save.isPending}>
              {save.isPending ? <Spinner /> : null}
              Save
            </Button>
          </CardFooter>
        </form>
      </Card>
    </>
  );
}
