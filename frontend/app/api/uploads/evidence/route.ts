/**
 * Proxy a complaint evidence upload to the platform API.
 *
 * Same reasoning as the patient bulk import: the multipart body is forwarded
 * with the session token attached server-side, because the browser cannot read
 * the httpOnly cookie the token lives in.
 */

import { NextResponse } from "next/server";

import { API_BASE_URL, sessionToken } from "@/lib/api";
import type { ApiEnvelope, UploadedFile } from "@/lib/types";

export async function POST(request: Request) {
  const token = await sessionToken();
  if (!token) {
    return NextResponse.json({ error: "Your session has expired. Sign in again." }, { status: 401 });
  }

  const incoming = await request.formData();
  const file = incoming.get("file");
  const evidenceType = String(incoming.get("evidence_type") ?? "");

  if (!(file instanceof File)) {
    return NextResponse.json({ error: "No file was attached." }, { status: 400 });
  }
  if (evidenceType !== "PHOTO" && evidenceType !== "VIDEO") {
    return NextResponse.json(
      { error: "Say whether this attachment is a photo or a video." },
      { status: 400 },
    );
  }

  const outgoing = new FormData();
  outgoing.append("file", file, file.name);
  outgoing.append("evidence_type", evidenceType);

  let upstream: Response;
  try {
    upstream = await fetch(`${API_BASE_URL}/uploads/evidence`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
      body: outgoing,
      cache: "no-store",
    });
  } catch {
    return NextResponse.json({ error: "The platform API is not reachable." }, { status: 503 });
  }

  const envelope = (await upstream
    .json()
    .catch(() => null)) as ApiEnvelope<UploadedFile> | null;

  if (!upstream.ok || !envelope?.success || !envelope.data) {
    return NextResponse.json(
      { error: envelope?.error ?? "The attachment could not be uploaded." },
      { status: upstream.status },
    );
  }

  return NextResponse.json({ file: envelope.data });
}
