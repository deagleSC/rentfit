import type { Metadata } from "next";

import { Prose } from "@/components/site";

export const metadata: Metadata = { title: "Terms" };

export default function Terms() {
  return (
    <Prose title="Terms" updated="17 November 2026">
      <p>RentFit is an early product, offered free and as is. By using it you agree to the following.</p>
      <h2>Listings</h2>
      <ul>
        <li>Listings shown in the apps today are sample data, not real homes.</li>
        <li>RentFit checks that a listing is complete and that its pin is inside the city. It does not inspect flats, verify landlords or handle money. Visit a home and check the landlord before paying anything.</li>
        <li>Landlords are responsible for what they publish and must have the right to rent the home.</li>
      </ul>
      <h2>AI answers</h2>
      <p>A language model reads messages and writes replies. Claims in search answers are checked against the listing or area note they cite, but descriptions come from landlords and area notes from OpenStreetMap, which can be out of date.</p>
      <h2>Fair use</h2>
      <p>Don't use RentFit to send spam, collect other people's details, or post homes you can't rent out. There are daily limits on AI use so the service stays available to everyone.</p>
      <h2>Changes</h2>
      <p>These terms may change as RentFit grows; the date above shows the latest version.</p>
    </Prose>
  );
}
