import { Button } from "@rentfit/ui/components/button";
import { ArrowRight, BadgeCheck, Languages, MapPinned, MessagesSquare, Route, ShieldCheck } from "lucide-react";
import Link from "next/link";

import { ChatMock } from "@/components/chat-mock";
import { LANDLORD_APP, TENANT_APP } from "@/components/links";
import { Feature, Section } from "@/components/site";

export default function Home() {
  return (
    <>
      <section className="mx-auto grid max-w-6xl items-center gap-10 px-4 py-14 sm:py-20 lg:grid-cols-[1.1fr_1fr]">
        <div className="space-y-6">
          <p className="text-sm font-medium text-primary">Bengaluru and Mumbai</p>
          <h1 className="text-4xl font-semibold tracking-tight sm:text-5xl">
            Describe the home you want. Get answers you can check.
          </h1>
          <p className="max-w-xl text-lg text-muted-foreground">
            Search rentals by chat, in English or Hinglish. Refine with follow-ups like “thoda sasta” or “near metro
            instead”, and see where every price and distance comes from.
          </p>
          <div className="flex flex-wrap gap-3">
            <Button asChild size="lg">
              <a href={TENANT_APP}>Find a home <ArrowRight /></a>
            </Button>
            <Button asChild size="lg" variant="outline">
              <a href={LANDLORD_APP}>List your flat</a>
            </Button>
          </div>
        </div>
        <ChatMock />
      </section>

      <Section eyebrow="For tenants" title="A search that remembers what you said"
               intro="Start broad and narrow down in conversation. RentFit keeps your filters as chips you can remove, and shows every result on a map.">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <Feature icon={<Languages />} title="Your words, not filters">
            “2 bhk Indiranagar 45k tak, family” works. So does “within 30 minutes of Manyata Tech Park”.
          </Feature>
          <Feature icon={<MessagesSquare />} title="Follow-ups that stick">
            “Cheaper”, “what about HSR instead”, or “the 2nd one's commute?” build on your last search.
          </Feature>
          <Feature icon={<BadgeCheck />} title="Facts with sources">
            Each claim in an answer links to the listing or area note it came from. A number that isn't in the source
            is never shown.
          </Feature>
          <Feature icon={<MapPinned />} title="Honest when it's thin">
            If too few homes match, RentFit widens one thing at a time, like the budget or nearby areas, and tells you
            what it changed.
          </Feature>
          <Feature icon={<Route />} title="Commute and area notes">
            See how far the nearest metro is, estimated commute times, and what's in the area, from OpenStreetMap.
          </Feature>
          <Feature icon={<ShieldCheck />} title="Your number stays private">
            Message landlords inside RentFit. Phone numbers and emails are removed from messages.
          </Feature>
        </div>
        <Link href="/tenants" className="mt-6 inline-flex items-center gap-1 text-sm font-medium text-primary hover:underline">
          How searching works <ArrowRight className="size-4" />
        </Link>
      </Section>

      <section className="border-y bg-muted/40">
        <Section eyebrow="For landlords" title="Write one message. Get a listing."
                 intro="Describe the flat the way you'd tell a friend. RentFit fills in the listing, asks only for what's missing, and checks your rent against nearby homes.">
          <div className="flex flex-wrap gap-3">
            <Button asChild><a href={LANDLORD_APP}>List your flat</a></Button>
            <Button asChild variant="outline"><Link href="/landlords">How listing works</Link></Button>
          </div>
        </Section>
      </section>

      <Section title="Questions" className="mx-auto max-w-3xl px-4 py-16 sm:py-20">
        <dl className="space-y-6">
          {FAQ.map(([q, a]) => (
            <div key={q}>
              <dt className="font-medium">{q}</dt>
              <dd className="mt-1 text-muted-foreground">{a}</dd>
            </div>
          ))}
        </dl>
      </Section>
    </>
  );
}

const FAQ: [string, string][] = [
  ["Which cities does RentFit cover?", "Bengaluru and Mumbai. Areas come from OpenStreetMap, so you can search by the locality names people actually use."],
  ["Is it free?", "Yes, for tenants and landlords. You need an account to search or list, so enquiries stay between real people."],
  ["Are the listings real?", "Not yet. RentFit is new, and the listings you see today are sample data, so you can try the search and the landlord tools."],
  ["Does RentFit verify listings?", "No. RentFit checks that a listing is complete and that its pin is in the city, but it doesn't inspect flats or verify landlords. Visit before you pay anything."],
  ["How is AI used?", "A language model reads your message and writes a short reply. Everything else is plain code: filters, search, distances, and checking each claim against its source."],
];
