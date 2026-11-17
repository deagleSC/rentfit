import type { Metadata } from "next";

import { Prose } from "@/components/site";

export const metadata: Metadata = { title: "Privacy" };

export default function Privacy() {
  return (
    <Prose title="Privacy" updated="17 November 2026">
      <p>This page explains what RentFit stores and why. RentFit is an early product; this is a plain description of how it works today, not legal advice.</p>
      <h2>What we store</h2>
      <ul>
        <li>Your account: email address, name, whether you're a tenant or a landlord, and your home city if you set one.</li>
        <li>Listings landlords create: the details, map pin and photos.</li>
        <li>Search chats: your messages, the filters they produced, and the results shown, so you can come back to a search.</li>
        <li>Shortlists, saved searches and enquiry messages.</li>
      </ul>
      <h2>What we remove</h2>
      <p>Phone numbers and email addresses are removed from listing descriptions, chat messages and enquiries before they are stored or shown to anyone else. They are also removed before any text is sent to the language model.</p>
      <h2>Who processes it</h2>
      <ul>
        <li>Supabase hosts the database, sign-in and photo storage.</li>
        <li>Vercel hosts the apps and the API.</li>
        <li>OpenRouter routes the text of your chat messages (with contacts removed) to the language model that reads and answers them.</li>
        <li>OpenStreetMap data and OpenFreeMap tiles provide the maps. Commute times may use OpenRouteService, which receives map coordinates only.</li>
      </ul>
      <h2>What we don't do</h2>
      <p>We don't sell your data, show ads, or share your contact details with landlords or tenants.</p>
      <h2>Deleting your data</h2>
      <p>To delete your account and everything linked to it, email <a href="mailto:supratik.deagle@gmail.com">supratik.deagle@gmail.com</a> from the address you signed up with, and we'll remove it.</p>
    </Prose>
  );
}
