import { Button } from "@rentfit/ui/components/button";
import { Bookmark, Heart, Languages, MapPinned, MessageSquare, ScanSearch } from "lucide-react";
import type { Metadata } from "next";

import { TENANT_APP } from "@/components/links";
import { Feature, Section, Steps } from "@/components/site";

export const metadata: Metadata = {
  title: "For tenants",
  description: "Search rentals in Bengaluru and Mumbai by chat, refine with follow-ups, and check every fact.",
};

export default function Tenants() {
  return (
    <>
      <Section eyebrow="For tenants" title="Find a rental by talking it through"
               intro="Tell RentFit what you need in a sentence. Refine it the way you would with a friend who knows the city."
               className="mx-auto max-w-6xl px-4 pt-14 pb-8 sm:pt-20">
        <Button asChild size="lg"><a href={TENANT_APP}>Start searching</a></Button>
      </Section>
      <Section title="How a search goes" className="mx-auto max-w-6xl px-4 py-10">
        <Steps items={[
          { title: "Say what you want", body: "“1 bhk for bachelors near Manyata, under 25k” or “Andheri West mein family ke liye 2 bhk”. If you leave out the city or budget, RentFit asks once." },
          { title: "Refine as you go", body: "Say “cheaper”, “near metro instead” or “also BTM Layout”. Your filters show as chips; remove one to widen the search." },
          { title: "Check and enquire", body: "Open a home for photos, nearby places and commute time. Shortlist it, compare, and message the landlord without sharing your number." },
        ]} />
      </Section>
      <Section title="What you get" className="mx-auto max-w-6xl px-4 py-10 pb-20">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <Feature icon={<Languages />} title="English or Hinglish">
            Slang works too: “thoda sasta” lowers your budget by about 10%, “metro ke paas” means within a kilometre of a station.
          </Feature>
          <Feature icon={<MapPinned />} title="Results on a map">
            Every result is a pin. Hover a card to find its pin, or move the map and search that area.
          </Feature>
          <Feature icon={<ScanSearch />} title="Answers you can check">
            Tap a source next to a claim to open the listing, or the OpenStreetMap note behind an area fact.
          </Feature>
          <Feature icon={<Heart />} title="Shortlist and compare">
            Keep the homes you like and compare rent, deposit, furnishing and metro distance side by side.
          </Feature>
          <Feature icon={<Bookmark />} title="Saved searches">
            Save a set of filters and reopen it later as a fresh search.
          </Feature>
          <Feature icon={<MessageSquare />} title="Enquiries, privately">
            Ask the landlord about a visit inside RentFit. Phone numbers and emails are removed from messages.
          </Feature>
        </div>
        <p className="mt-8 max-w-2xl text-sm text-muted-foreground">
          Commute times come from a routing service when available, and otherwise from distance. Estimates are labelled.
          RentFit doesn't inspect flats, so visit before you pay anything.
        </p>
      </Section>
    </>
  );
}
