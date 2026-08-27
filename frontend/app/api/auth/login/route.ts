/**
 * Exchange credentials for a session cookie.
 *
 * The browser never sees the access token. It is posted here, forwarded to the
 * platform API, and the token that comes back is stored in an httpOnly cookie.
 * An XSS in a dashboard view therefore cannot read a ministry session out of
 * `document.cookie` or `localStorage`.
 *
 * A second, readable cookie carries only the role, so middleware can gate
 * routes without a round trip. It is not a credential: forging it grants
 * nothing, because every API call is still authorised by the signed token.
 */

import { NextResponse } from "next/server";

import { API_BASE_URL, ROLE_COOKIE, SESSION_COOKIE } from "@/lib/api";
import type { ApiEnvelope, TokenResponse, UserRole } from "@/lib/types";

interface LoginBody {
  email?: string;
  password?: string;
  portal?: "government" | "hospital" | "citizen";
}

export async function POST(request: Request) {
  let body: LoginBody;
  try {
    body = (await request.json()) as LoginBody;
  } catch {
    return NextResponse.json({ error: "The sign-in request was malformed." }, { status: 400 });
  }

  const email = body.email?.trim();
  const password = body.password;

  if (!email || !password) {
    return NextResponse.json(
      { error: "Enter both your email address and your password." },
      { status: 400 },
    );
  }

  // The government portal has its own endpoint, which pins the expected role.
  const isGovernment = body.portal === "government";
  const endpoint = isGovernment ? "/auth/govt/login" : "/auth/login";
  const payload = isGovernment
    ? { official_email: email, password }
    : { email, password };

  let upstream: Response;
  try {
    upstream = await fetch(`${API_BASE_URL}${endpoint}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      cache: "no-store",
    });
  } catch {
    return NextResponse.json(
      { error: "The platform API is not reachable. Check that the backend is running." },
      { status: 503 },
    );
  }

  const envelope = (await upstream.json().catch(() => null)) as ApiEnvelope<TokenResponse> | null;

  if (!upstream.ok || !envelope?.success || !envelope.data) {
    return NextResponse.json(
      { error: envelope?.error ?? "Sign-in failed." },
      { status: upstream.status === 200 ? 401 : upstream.status },
    );
  }

  const token = envelope.data;
  const response = NextResponse.json({ role: token.role, landing: landingFor(token.role) });
  const secure = process.env.NODE_ENV === "production";

  response.cookies.set(SESSION_COOKIE, token.access_token, {
    httpOnly: true,
    sameSite: "lax",
    secure,
    path: "/",
    maxAge: token.expires_in_seconds,
  });

  response.cookies.set(ROLE_COOKIE, token.role, {
    httpOnly: false,
    sameSite: "lax",
    secure,
    path: "/",
    maxAge: token.expires_in_seconds,
  });

  return response;
}

/** Where an account lands after signing in. */
function landingFor(role: UserRole): string {
  if (role === "GOVT_ADMIN") return "/gov/hospitals";
  if (role === "CITIZEN") return "/citizen/health-record";
  return "/hospital";
}
