import { ArrowRight } from "lucide-react";
import Link from "next/link";

import { LANDLORD_APP, TENANT_APP } from "@/components/links";
import { Container, Rows, Shot } from "@/components/site";
import listingShot from "@/public/shots/listing.png";
import searchShot from "@/public/shots/search.png";

const HEARD: { say: string; hears: string[] }[] = [
  { say: "2 bhk in Koramangala under 40k, near metro", hears: ["Koramangala", "2 BHK", "Up to ₹40k", "Metro ≤ 1 km"] },
  { say: "Bengaluru mein 1 bhk chahiye, 25 hazaar tak, bachelor hu", hears: ["in Bengaluru", "1 BHK", "Up to ₹25k", "Bachelors OK"] },
  { say: "thoda sasta", hears: ["Up to ₹36k (was ₹40k)", "everything else kept"] },
  { say: "what about HSR instead", hears: ["HSR Layout", "replaces Koramangala"] },
  { say: "the 2nd one's commute?", hears: ["answers about result 2", "no new search"] },
];

export default function Home() {
  return (
    <>
      <Container className="pt-16 pb-12 sm:pt-24">
        <h1 className="display max-w-4xl text-5xl sm:text-7xl">
          Describe the flat you want. <span className="italic text-primary">RentFit does the searching.</span>
        </h1>
        <div className="mt-8 grid gap-8 sm:grid-cols-[1fr_auto] sm:items-end">
          <p className="max-w-xl text-lg text-muted-foreground">
            RentFit is rental search you talk to, for Bengaluru and Mumbai. Ask in English or Hinglish, refine as you
            go, and see where every price and distance came from.
          </p>
          <div className="flex flex-wrap items-center gap-x-6 gap-y-3 text-sm font-medium">
            <a href={TENANT_APP} className="inline-flex items-center gap-1.5 rounded-md bg-primary px-4 py-2.5 text-primary-foreground hover:bg-primary/90">
              Start a search <ArrowRight className="size-4" />
            </a>
            <a href={LANDLORD_APP} className="text-foreground underline-offset-4 hover:underline">I have a flat to rent</a>
          </div>
        </div>
      </Container>

      <Container className="pb-20">
        <Shot src={searchShot} alt="RentFit search: filter chips, a reply with numbered sources, two listing cards and their pins on a map of Bengaluru" priority />
        <p className="mt-3 text-sm text-muted-foreground">
          A real search. When too few homes match, RentFit loosens one thing at a time and says what it changed.
        </p>
      </Container>

      <section className="border-y bg-muted/40">
        <Container className="grid gap-10 py-20 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
          <div>
            <h2 className="display text-4xl sm:text-5xl">You type. It listens.</h2>
            <p className="mt-4 max-w-sm text-muted-foreground">
              Each message turns into filters you can see and remove. Follow-ups change the last search instead of
              starting over.
            </p>
          </div>
          <ol className="divide-y border-y bg-background">
            {HEARD.map((h) => (
              <li key={h.say} className="grid gap-3 px-4 py-4 sm:grid-cols-2 sm:gap-6">
                <p className="font-medium">“{h.say}”</p>
                <p className="flex flex-wrap gap-1.5">
                  {h.hears.map((x) => (
                    <span key={x} className="rounded border px-2 py-0.5 text-sm text-muted-foreground">{x}</span>
                  ))}
                </p>
              </li>
            ))}
          </ol>
        </Container>
      </section>

      <Container className="grid items-center gap-10 py-20 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
        <div>
          <h2 className="display text-4xl sm:text-5xl">Listing a flat is one message.</h2>
          <p className="mt-4 max-w-sm text-muted-foreground">
            Write it the way you'd say it on the phone. RentFit fills in the listing, asks for what's missing, and shows
            how your rent compares with similar homes nearby. Nothing goes live until you press Publish.
          </p>
          <Link href="/landlords" className="mt-6 inline-flex items-center gap-1 text-sm font-medium text-primary hover:underline">
            How listing works <ArrowRight className="size-4" />
          </Link>
        </div>
        <Shot src={listingShot} alt="RentFit landlord app: a one-message description beside the listing preview it produced" />
      </Container>

      <section className="border-t">
        <Container className="py-20">
          <h2 className="display text-4xl sm:text-5xl">Plainly</h2>
          <div className="mt-10">
            <Rows items={[
              { term: "Where it works", detail: "Bengaluru and Mumbai. Area names come from OpenStreetMap, so the names people use work." },
              { term: "What it costs", detail: "Nothing, for tenants or landlords. You need an account, so messages stay between real people." },
              { term: "The listings", detail: "Sample data for now. RentFit is new; try the search and the landlord tools with it." },
              { term: "What it doesn't check", detail: "RentFit doesn't inspect flats or verify landlords. Visit before you pay anything." },
              { term: "Your number", detail: "Never shared. Phone numbers and emails are removed from every message, on both sides." },
              { term: "Where AI fits", detail: "A language model reads your message and writes the reply. Search, distances and the check that every number matches its source are ordinary code." },
            ]} />
          </div>
        </Container>
      </section>
    </>
  );
}
