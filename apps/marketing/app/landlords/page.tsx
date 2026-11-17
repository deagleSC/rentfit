import { ArrowRight } from "lucide-react";
import type { Metadata } from "next";

import { LANDLORD_APP } from "@/components/links";
import { Container, Rows, Shot } from "@/components/site";
import listingShot from "@/public/shots/listing.png";

export const metadata: Metadata = {
  title: "Listing",
  description: "List a flat in Bengaluru or Mumbai by describing it in chat. Free.",
};

export default function Landlords() {
  return (
    <>
      <Container className="pt-16 pb-12 sm:pt-24">
        <h1 className="display max-w-3xl text-5xl sm:text-6xl">Describe the flat. Skip the form.</h1>
        <p className="mt-6 max-w-xl text-lg text-muted-foreground">
          One message gets you most of a listing. RentFit asks for what's missing, you drop a pin and add photos, and
          you publish when it looks right.
        </p>
        <a href={LANDLORD_APP} className="mt-8 inline-flex items-center gap-1.5 rounded-md bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground hover:bg-primary/90">
          List your flat <ArrowRight className="size-4" />
        </a>
      </Container>
      <Container className="pb-16">
        <Shot src={listingShot} alt="A landlord's one-message description beside the listing preview RentFit filled in" priority />
      </Container>
      <Container className="pb-24">
        <Rows items={[
          { term: "One message to start", detail: "“2BHK in Indiranagar, rent 42k, 3 months deposit, semi furnished, bachelors also ok.” The preview fills in and changed fields are highlighted. Then it asks for the next thing it needs." },
          { term: "Edits in plain words", detail: "“Bachelors also ok”, “make deposit 2 months”, “remove the gym”. Chat edits and the edit form change the listing the same way." },
          { term: "Pin and photos", detail: "Drop a pin; it decides the locality, so tenants searching that area find you. If it disagrees with the area you named, RentFit asks which is right. Add 3 to 15 photos, resized on your phone before upload." },
          { term: "A rent check", detail: "See the range for similar homes nearby, with the listings it's based on. If there aren't enough, it says the number is an estimate." },
          { term: "Enquiries in one inbox", detail: "Tenants message you inside RentFit and you reply there. Phone numbers and emails are removed from messages on both sides." },
          { term: "You decide what's live", detail: "Nothing is published until you press Publish. Pause, resume, or mark it as let whenever you like." },
        ]} />
      </Container>
    </>
  );
}
