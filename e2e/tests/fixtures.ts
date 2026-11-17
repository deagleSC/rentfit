import AxeBuilder from "@axe-core/playwright";
import { expect, type Browser, type Page } from "@playwright/test";
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

const ENV_FILE = path.resolve(import.meta.dirname, "../../apps/api/.env");

export const env: Record<string, string> = Object.fromEntries(
  fs.readFileSync(ENV_FILE, "utf8").split("\n")
    .filter((l) => l.includes("=") && !l.startsWith("#"))
    .map((l) => [l.slice(0, l.indexOf("=")), l.slice(l.indexOf("=") + 1)]),
);

const ERRORS = new WeakMap<Page, string[]>();

export const LANDLORD = "http://localhost:3000";
export const TENANT = "http://localhost:3001";

/** Sign in on a fresh context; fail the test on any uncaught page error. */
export async function signIn(browser: Browser, app: string, email: string, password: string): Promise<Page> {
  const page = await (await browser.newContext()).newPage();
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  ERRORS.set(page, errors);
  await page.goto(`${app}/sign-in`);
  await page.fill("input[type=email]", email);
  await page.fill("input[type=password]", password);
  await page.click("button[type=submit]");
  await page.waitForURL((u) => !u.pathname.startsWith("/sign-in"));
  return page;
}

export function noPageErrors(page: Page): void {
  expect(ERRORS.get(page) ?? []).toEqual([]);
}

/** Fail on serious or critical axe violations (frontend plan §10). The map canvas is third-party. */
export async function expectAccessible(page: Page, name: string): Promise<void> {
  const result = await new AxeBuilder({ page }).exclude(".maplibregl-map").analyze();
  const bad = result.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  const detail = bad.flatMap((v) => v.nodes.slice(0, 4).map((n) =>
    `${name}: ${v.id} ${n.target.join(" ")} — ${(n.any[0]?.message ?? n.failureSummary ?? "").slice(0, 160)}`));
  expect(detail).toEqual([]);
}

/** Run SQL as the database owner (cleanup only). */
export function sql(query: string): string {
  return execFileSync("psql", [env.TEST_ADMIN_DATABASE_URL!, "-Atc", query], { encoding: "utf8" }).trim();
}

/** Remove what the e2e tenant created: chats (and their checkpoints), enquiries, shortlists, saved searches. */
export function cleanTenant(): void {
  const t = `(select id from auth.users where email = '${env.E2E_TENANT_EMAIL}')`;
  const threads = `(select thread_id from chats where owner_id in ${t} and kind = 'search')`;
  sql(`delete from checkpoint_writes where thread_id in ${threads};
       delete from checkpoint_blobs where thread_id in ${threads};
       delete from checkpoints where thread_id in ${threads};
       delete from notifications where entity_id in (select id from enquiries where tenant_id in ${t});
       delete from enquiries where tenant_id in ${t};
       delete from shortlists where tenant_id in ${t};
       delete from saved_searches where tenant_id in ${t};
       delete from chats where owner_id in ${t} and kind = 'search';`);
}

/** Remove the e2e landlord's listings (photos in memory storage vanish with the dev API). */
export function cleanLandlord(): void {
  const l = `(select id from auth.users where email = '${env.E2E_LANDLORD_EMAIL}')`;
  const threads = `(select thread_id from chats where owner_id in ${l} and kind = 'listing')`;
  sql(`delete from checkpoint_writes where thread_id in ${threads};
       delete from checkpoint_blobs where thread_id in ${threads};
       delete from checkpoints where thread_id in ${threads};
       delete from listings where landlord_id in ${l};`);
}
