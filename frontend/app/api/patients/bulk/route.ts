/**
 * Proxy a patient file upload to the platform API.
 *
 * The browser cannot call the API directly with credentials: the session token
 * lives in an httpOnly cookie it is not allowed to read. The multipart body is
 * forwarded here unchanged, with the token attached server-side.
 */

import { NextResponse } from "next/server";

import { API_BASE_URL, sessionToken } from "@/lib/api";
import type { ApiEnvelope, BulkUploadReport } from "@/lib/types";

export async function POST(request: Request) {
  const token = await sessionToken();
  if (!token) {
    return NextResponse.json({ error: "Your session has expired. Sign in again." }, { status: 401 });
  }

  const incoming = await request.formData();
  const file = incoming.get("file");
  const hospitalId = String(incoming.get("hospital_id") ?? "");

  if (!(file instanceof File)) {
    return NextResponse.json({ error: "No file was attached." }, { status: 400 });
  }
  if (!hospitalId) {
    return NextResponse.json({ error: "No hospital was named." }, { status: 400 });
  }

  const outgoing = new FormData();
  outgoing.append("file", file, file.name);

  let upstream: Response;
  try {
    upstream = await fetch(`${API_BASE_URL}/hospitals/${hospitalId}/patients/bulk`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
      body: outgoing,
      cache: "no-store",
    });
  } catch {
    return NextResponse.json(
      { error: "The platform API is not reachable." },
      { status: 503 },
    );
  }

  const envelope = (await upstream
    .json()
    .catch(() => null)) as ApiEnvelope<BulkUploadReport> | null;

  if (!upstream.ok || !envelope?.success || !envelope.data) {
    return NextResponse.json(
      { error: envelope?.error ?? "The file could not be imported." },
      { status: upstream.status },
    );
  }

  return NextResponse.json({ report: envelope.data });
}
