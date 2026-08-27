/** Clear the session. Both cookies are expired, then the caller is redirected. */

import { NextResponse } from "next/server";

import { ROLE_COOKIE, SESSION_COOKIE } from "@/lib/api";

export async function POST(request: Request) {
  const response = NextResponse.redirect(new URL("/login", request.url), { status: 303 });
  response.cookies.set(SESSION_COOKIE, "", { path: "/", maxAge: 0 });
  response.cookies.set(ROLE_COOKIE, "", { path: "/", maxAge: 0 });
  return response;
}
