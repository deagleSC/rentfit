import { expect, test, type Locator, type Page } from "@playwright/test";

import { TENANT, cleanTenant, env, expectAccessible, noPageErrors, signIn } from "./fixtures";

test.beforeAll(() => cleanTenant());
test.afterAll(() => cleanTenant());

async function say(page: Page, text: string): Promise<Locator> {
  const n = await page.getByTestId("assistant-turn").count();
  await page.getByLabel("Message").fill(text);
  await page.getByLabel("Send", { exact: true }).click();
  const turn = page.getByTestId("assistant-turn").nth(n);
  await expect(turn).toBeVisible();
  await expect(page.getByText("Searching…")).toHaveCount(0, { timeout: 90_000 });
  return turn;
}

test("tenant: 3-turn search, pins match cards, citations open their source", async ({ browser }) => {
  const page = await signIn(browser, TENANT, env.E2E_TENANT_EMAIL!, env.E2E_TENANT_PASSWORD!);
  await expect(page.getByRole("heading", { name: "Find a home" })).toBeVisible();
  await expectAccessible(page, "search (empty)");

  let turn = await say(page, "2 BHK in Koramangala under 40k");
  await expect(page).toHaveURL(/\/search\//);
  const cards = turn.getByTestId("listing-card");
  expect(await cards.count()).toBeGreaterThan(0);
  expect(await page.getByTestId("listing-pin").count()).toBeGreaterThanOrEqual(await cards.count());
  await expect(page.getByLabel("Active filters")).toContainText("Up to ₹40k");

  const cites = turn.getByTestId("citation");
  for (let i = 0; i < (await cites.count()); i++) {
    await cites.nth(i).click();
    await expect(page.getByTestId("citation-source")).toContainText(/Open listing|OpenStreetMap/);
    await page.keyboard.press("Escape");
  }
  await cards.first().hover();
  await expect(page.locator("[data-testid=listing-pin][data-active]")).toHaveCount(1);
  await expectAccessible(page, "search (results)");

  turn = await say(page, "thoda sasta");
  await expect(page.getByLabel("Active filters")).toContainText("Up to ₹36k");

  turn = await say(page, "what about the 2nd one?");
  await expect(turn.getByTestId("listing-card")).toHaveCount(1);

  await page.getByRole("button", { name: /^Remove 2 BHK/ }).click();
  await expect(page.getByText("Searching…")).toHaveCount(0, { timeout: 90_000 });
  await expect(page.getByLabel("Active filters")).not.toContainText("2 BHK");

  await page.reload();
  await expect(page.getByTestId("assistant-turn")).toHaveCount(4);
  noPageErrors(page);
});
