import { ArrowRight } from "lucide-react";
import type { Metadata } from "next";

import { TENANT_APP } from "@/components/links";
import { Container, Rows, Shot } from "@/components/site";
import searchShot from "@/public/shots/search.png";

export const metadata: Metadata = {
  title: "Renting",
  description: "Search rentals in Bengaluru and Mumbai by chat, refine with follow-ups, and check every fact.",
};

export default function Tenants() {
  return (
    <>
      <Container className="pt-16 pb-12 sm:pt-24">
        <h1 className="display max-w-3xl text-5xl sm:text-6xl">Search the way you'd ask a friend who knows the city.</h1>
        <p className="mt-6 max-w-2xl text-lg text-muted-foreground">
          Start with a sentence. Narrow it down in conversation. Open a home, shortlist it, and message the landlord
          without giving out your number.
        </p>
        <a href={TENANT_APP} className="mt-8 inline-flex items-center gap-1.5 rounded-md bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground hover:bg-primary/90">
          Start a search <ArrowRight className="size-4" />
        </a>
      </Container>
      <Container className="pb-16">
        <Shot src={searchShot} alt="RentFit search results with sources and a map" priority />
      </Container>
      <Container className="pb-24">
        <Rows items={[
          { term: "Your words, not dropdowns", detail: "“1 bhk for bachelors near Manyata, under 25k” works, and so does Hinglish. Leave out the city or budget and RentFit asks once; set a home city and it won't need to." },
          { term: "Follow-ups that stick", detail: "“Cheaper” takes about 10% off your budget. “Near metro instead” keeps everything else. Your filters sit above the chat as chips; remove one to widen the search." },
          { term: "Sources on every claim", detail: "Each point in a reply has a numbered source: the listing, or an OpenStreetMap note about the area. A number that isn't in its source is dropped before you see it." },
          { term: "When there isn't enough", detail: "If fewer than five homes match, RentFit loosens one thing at a time (budget, nearby areas, commute, metro distance) and tells you what it changed. It never loosens what you just asked for." },
          { term: "Map, commute, area", detail: "Every result is a pin. Move the map and search that area. A home's page shows nearby stations and offices, commute time to one you pick, and what's in the area." },
          { term: "Shortlist, saved searches, enquiries", detail: "Compare shortlisted homes side by side, reopen a saved search later, and message landlords inside RentFit. Contact details are removed from messages." },
        ]} />
        <p className="mt-6 max-w-2xl text-sm text-muted-foreground">
          Commute times come from a routing service when it's available and from distance otherwise; estimates are
          labelled. RentFit doesn't inspect flats, so visit before you pay anything.
        </p>
      </Container>
    </>
  );
}
