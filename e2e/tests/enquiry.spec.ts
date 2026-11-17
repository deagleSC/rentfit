import { expect, test } from "@playwright/test";

import { LANDLORD, TENANT, cleanTenant, env, expectAccessible, noPageErrors, signIn, sql } from "./fixtures";

test.beforeAll(() => cleanTenant());
test.afterAll(() => cleanTenant());

test("enquiry: tenant asks (contacts stripped), landlord replies, tenant sees it", async ({ browser }) => {
  // A seeded listing; its seed landlord answers.
  const [listingId, landlordEmail] = sql(
    "select l.id || '|' || u.email from listings l join auth.users u on u.id = l.landlord_id" +
    " where l.status = 'published' and u.email like 'seed-landlord-%' order by l.published_at limit 1").split("|");

  const tenant = await signIn(browser, TENANT, env.E2E_TENANT_EMAIL!, env.E2E_TENANT_PASSWORD!);
  await tenant.goto(`${TENANT}/listings/${listingId}`);
  await expect(tenant.getByText("Contact the landlord")).toBeVisible();
  await expectAccessible(tenant, "listing detail");
  await tenant.getByRole("button", { name: "Shortlist", exact: true }).click();
  await expect(tenant.getByRole("button", { name: "Shortlisted" })).toBeVisible();
  await tenant.getByLabel("Message to the landlord").fill("Is it available? Call me on 98765 43210.");
  await tenant.getByRole("button", { name: "Send enquiry" }).click();
  await expect(tenant.getByRole("link", { name: "Open your enquiry" })).toBeVisible();

  const landlord = await signIn(browser, LANDLORD, landlordEmail!, env.SEED_PASSWORD!);
  await landlord.goto(`${LANDLORD}/enquiries`);
  const first = landlord.getByTestId("enquiry-message").first();
  await expect(first).toContainText("[contact removed]");
  await expect(first).not.toContainText("98765");
  await expectAccessible(landlord, "landlord enquiries");
  await landlord.getByPlaceholder("Write a reply…").fill("Yes, come on Saturday at 11.");
  await landlord.getByRole("button", { name: "Send reply" }).click();
  await expect(landlord.getByTestId("enquiry-message")).toHaveCount(2);

  await tenant.goto(`${TENANT}/enquiries`);
  await expect(tenant.getByTestId("enquiry-message").nth(1)).toContainText("Saturday at 11");
  noPageErrors(tenant);
  noPageErrors(landlord);
});
