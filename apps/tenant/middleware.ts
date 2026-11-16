import type { NextRequest } from "next/server";

import { handleSession } from "./lib/session-middleware";

// Login is required everywhere (no anonymous search), except the auth pages.
export function middleware(request: NextRequest) {
  return handleSession(request, "tenant", [], "/");
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp|ico)$).*)"],
};
