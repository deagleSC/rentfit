// Bundle budget (frontend plan §10): first-load JS per route, from `next build` output.
//   pnpm turbo run build --filter=@rentfit/landlord --filter=@rentfit/tenant | tee build.log
//   node scripts/check-bundle.mjs build.log
import fs from "node:fs";

const BUDGET_KB = {
  "@rentfit/tenant": { "/": 350, "/search/[chatId]": 350, "*": 400 },
  "@rentfit/landlord": { "*": 400 },
  "@rentfit/marketing": { "*": 250 }, // static pages, no app code
};

const lines = fs.readFileSync(process.argv[2] ?? "build.log", "utf8").split("\n");
const row = /^(@rentfit\/\w+):build: [├└┌]\s+[ƒ○●]\s+(\S+)\s+[\d.]+\s+k?B\s+([\d.]+)\s+(kB|MB)/;
let failed = false;
let seen = 0;
for (const line of lines) {
  const m = line.match(row);
  if (!m) continue;
  const [, app, route, size, unit] = m;
  const kb = Number(size) * (unit === "MB" ? 1024 : 1);
  const budgets = BUDGET_KB[app];
  if (!budgets) continue;
  const limit = budgets[route] ?? budgets["*"];
  seen++;
  const ok = kb <= limit;
  if (!ok) failed = true;
  console.log(`${ok ? "ok  " : "OVER"} ${app} ${route} ${kb} kB (budget ${limit} kB)`);
}
if (!seen) {
  console.error("No route table found in the build log.");
  process.exit(1);
}
process.exit(failed ? 1 : 0);
