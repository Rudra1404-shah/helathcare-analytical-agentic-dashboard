/**
 * Route gating.
 *
 * This is a convenience, not the security boundary. It keeps a citizen from
 * loading the ministry shell and seeing empty panels, and sends a signed-out
 * visitor to the login page instead of an error. The real enforcement is in
 * the API, which checks the signed token on every single request and would
 * refuse the data even if somebody edited the readable role cookie by hand.
 */

import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

const SESSION_COOKIE = "unhp_session";
const ROLE_COOKIE = "unhp_role";

const PORTAL_ROLES: Record<string, readonly string[]> = {
  "/gov": ["GOVT_ADMIN"],
  "/hospital": ["GOVT_ADMIN", "HOSPITAL_ADMIN", "HOSPITAL_STAFF", "DOCTOR"],
  "/citizen": ["CITIZEN", "GOVT_ADMIN"],
};

const LANDING: Record<string, string> = {
  GOVT_ADMIN: "/gov/hospitals",
  HOSPITAL_ADMIN: "/hospital",
  HOSPITAL_STAFF: "/hospital",
  DOCTOR: "/hospital",
  CITIZEN: "/citizen/health-record",
};

export default function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;

  const portal = Object.keys(PORTAL_ROLES).find(
    (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`),
  );
  if (!portal) return NextResponse.next();

  const session = request.cookies.get(SESSION_COOKIE)?.value;
  if (!session) {
    const login = new URL("/login", request.url);
    login.searchParams.set("next", pathname);
    return NextResponse.redirect(login);
  }

  const role = request.cookies.get(ROLE_COOKIE)?.value ?? "";
  if (!PORTAL_ROLES[portal].includes(role)) {
    return NextResponse.redirect(new URL(LANDING[role] ?? "/login", request.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/gov/:path*", "/hospital/:path*", "/citizen/:path*"],
};
