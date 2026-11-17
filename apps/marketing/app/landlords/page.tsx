import { Button } from "@rentfit/ui/components/button";
import { Camera, IndianRupee, MapPin, MessageSquare, MessagesSquare, PauseCircle } from "lucide-react";
import type { Metadata } from "next";

import { LANDLORD_APP } from "@/components/links";
import { Feature, Section, Steps } from "@/components/site";

export const metadata: Metadata = {
  title: "For landlords",
  description: "List a flat in Bengaluru or Mumbai by describing it in chat. Free.",
};

export default function Landlords() {
  return (
    <>
      <Section eyebrow="For landlords" title="List your flat by describing it"
               intro="No long form to start with. Write what you'd say on the phone and RentFit builds the listing as you go."
               className="mx-auto max-w-6xl px-4 pt-14 pb-8 sm:pt-20">
        <Button asChild size="lg"><a href={LANDLORD_APP}>List your flat</a></Button>
      </Section>
      <Section title="From message to published" className="mx-auto max-w-6xl px-4 py-10">
        <Steps items={[
          { title: "Describe it", body: "“2BHK in Koramangala, 35k rent, 2 months deposit, semi furnished, family only.” A preview fills in beside the chat, and RentFit asks for anything still missing." },
          { title: "Pin and add photos", body: "Drop a pin on the map and add 3 to 15 photos; they're resized on your phone before upload. If the pin and the area you named disagree, RentFit asks which is right." },
          { title: "Check and publish", body: "Compare your rent with similar homes nearby, fix anything in chat or in the form, and publish. Pause or mark it as let any time." },
        ]} />
      </Section>
      <Section title="What you get" className="mx-auto max-w-6xl px-4 py-10 pb-20">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <Feature icon={<MessagesSquare />} title="Edits in plain words">
            “Bachelors also ok”, “make deposit 2 months”, “remove the gym”. Each change shows in the preview before you publish.
          </Feature>
          <Feature icon={<IndianRupee />} title="A rent check">
            See the range for comparable homes within a few kilometres, with the listings it's based on. When there aren't enough, it says it's an estimate.
          </Feature>
          <Feature icon={<MapPin />} title="The right area">
            The pin decides the locality, so tenants searching for that area find you.
          </Feature>
          <Feature icon={<Camera />} title="Photos without fuss">
            Upload straight from your phone. Photos are resized before upload.
          </Feature>
          <Feature icon={<MessageSquare />} title="Enquiries in one inbox">
            Tenants message you inside RentFit and you reply there. Contact details are removed from messages on both sides.
          </Feature>
          <Feature icon={<PauseCircle />} title="You stay in control">
            Nothing is published until you press Publish. Pause a listing, resume it, or mark it as let.
          </Feature>
        </div>
      </Section>
    </>
  );
}
