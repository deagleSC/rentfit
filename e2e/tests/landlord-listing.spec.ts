import { expect, test } from "@playwright/test";

import { LANDLORD, cleanLandlord, env, expectAccessible, noPageErrors, signIn } from "./fixtures";

test.afterAll(() => cleanLandlord());

test("landlord: chat → edit → pin → photos → form edit → publish", async ({ browser }) => {
  const page = await signIn(browser, LANDLORD, env.E2E_LANDLORD_EMAIL!, env.E2E_LANDLORD_PASSWORD!);
  await expect(page.getByRole("heading", { name: "Your listings" })).toBeVisible();
  await expectAccessible(page, "listings");

  await page.getByRole("button", { name: "New listing" }).first().click();
  await page.waitForURL(/\/listings\//);

  await page.getByLabel("Message").fill(
    "2BHK in Koramangala, rent 35k, 2 months deposit, semi furnished, family only. Lift and gym. Ready to move.");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByText(/Got it: .*Koramangala/)).toBeVisible();
  await expect(page.locator('[data-field="rent"]')).toContainText("35,000");
  await expect(page.locator('[data-field="deposit"]')).toContainText("70,000");

  await page.getByLabel("Message").fill("bachelors also ok");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.locator('[data-field="tenant_pref"]')).toContainText("Anyone");

  const map = page.locator(".maplibregl-canvas").last();
  await map.scrollIntoViewIfNeeded();
  await page.waitForTimeout(1500); // tiles and handlers settle
  const box = (await map.boundingBox())!;
  await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
  await expect(page.getByTestId("listing-pin")).toBeVisible();

  const photos = ["1-living-room", "2-bedroom", "3-kitchen"].map(
    (n) => new URL(`../../apps/api/scripts/seed_data/photos/${n}.webp`, import.meta.url).pathname);
  await page.getByLabel("Choose photos").setInputFiles(photos);
  await expect(page.getByRole("img", { name: "Photo 3" })).toBeVisible();

  await page.getByRole("button", { name: "Edit details" }).click();
  await page.getByLabel("Maintenance (₹/month)").fill("2500");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.locator('[data-field="maintenance"]')).toContainText("2,500");
  await expectAccessible(page, "listing");

  await page.getByRole("button", { name: "Publish" }).click();
  await expect(page.getByText("Published", { exact: true }).first()).toBeVisible();
  noPageErrors(page);
});
