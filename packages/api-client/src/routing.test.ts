import { describe, expect, it } from "vitest";

import { decideRoute, matchesPath, safeNextPath } from "./routing";

const landlord = { app: "landlord" as const, publicPaths: [] };
const tenant = { app: "tenant" as const, publicPaths: ["/privacy"] };

describe("matchesPath", () => {
  it("matches exact paths and sub-paths, not prefixes of words", () => {
    expect(matchesPath("/listings", "/listings")).toBe(true);
    expect(matchesPath("/listings/123", "/listings")).toBe(true);
    expect(matchesPath("/listingsx", "/listings")).toBe(false);
    expect(matchesPath("/", "/")).toBe(true);
    expect(matchesPath("/anything", "/")).toBe(false);
  });
});

describe("decideRoute", () => {
  it("sends signed-out users to sign in, keeping where they were going", () => {
    expect(decideRoute({ ...landlord, pathname: "/listings/new", signedIn: false, role: null })).toEqual({
      type: "sign-in",
      next: "/listings/new",
    });
  });

  it("lets signed-out users see auth pages and public pages", () => {
    expect(decideRoute({ ...landlord, pathname: "/sign-in", signedIn: false, role: null }).type).toBe("next");
    expect(decideRoute({ ...tenant, pathname: "/privacy", signedIn: false, role: null }).type).toBe("next");
  });

  it("requires login for search (no anonymous search)", () => {
    expect(decideRoute({ ...tenant, pathname: "/", signedIn: false, role: null }).type).toBe("sign-in");
    expect(decideRoute({ ...tenant, pathname: "/shortlist", signedIn: false, role: null }).type).toBe(
      "sign-in",
    );
  });

  it("redirects a user with the other role to the other app", () => {
    expect(decideRoute({ ...landlord, pathname: "/", signedIn: true, role: "tenant" })).toEqual({
      type: "other-app",
    });
    expect(decideRoute({ ...tenant, pathname: "/listings", signedIn: true, role: "landlord" })).toEqual({
      type: "other-app",
    });
  });

  it("sends signed-in users away from the auth pages", () => {
    expect(decideRoute({ ...landlord, pathname: "/sign-in", signedIn: true, role: "landlord" }).type).toBe("home");
  });

  it("lets signed-in users with no role metadata through, so the profile can be completed", () => {
    expect(decideRoute({ ...landlord, pathname: "/", signedIn: true, role: undefined }).type).toBe("next");
  });
});

describe("safeNextPath", () => {
  it("keeps same-site paths", () => {
    expect(safeNextPath("/listings/1?tab=a")).toBe("/listings/1?tab=a");
  });
  it("rejects absolute and protocol-relative URLs", () => {
    expect(safeNextPath("https://evil.test")).toBe("/");
    expect(safeNextPath("//evil.test")).toBe("/");
    expect(safeNextPath("/\\evil.test")).toBe("/");
    expect(safeNextPath(null, "/shortlist")).toBe("/shortlist");
  });
});
