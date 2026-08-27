"use server";

import { revalidatePath } from "next/cache";

import { apiTry } from "@/lib/api";
import type { Complaint, EvidenceType } from "@/lib/types";

interface UploadedAttachment {
  url: string;
  file_name: string;
  content_type: string;
  size_bytes: number;
  checksum_sha256: string;
  evidence_type: EvidenceType;
}

export interface ComplaintResult {
  ok: boolean;
  complaintNumber?: string;
  error?: string;
}

/**
 * File a public complaint.
 *
 * The mandatory-evidence rule is checked here as well as in the API, because a
 * citizen should hear it in plain language before the round trip. The API
 * enforces it twice more, so no client can bypass it.
 */
export async function submitComplaint(formData: FormData): Promise<ComplaintResult> {
  let evidence: UploadedAttachment[];
  try {
    evidence = JSON.parse(String(formData.get("evidence") ?? "[]")) as UploadedAttachment[];
  } catch {
    evidence = [];
  }

  if (evidence.length === 0) {
    return {
      ok: false,
      error:
        "A complaint cannot be submitted without evidence. Attach at least one photograph or video.",
    };
  }

  const hospitalId = String(formData.get("hospital_id") ?? "").trim();
  if (!hospitalId) {
    return { ok: false, error: "Choose the hospital this complaint is about." };
  }

  const incidentLocal = String(formData.get("incident_at") ?? "").trim();
  if (!incidentLocal) {
    return { ok: false, error: "Say when the incident happened." };
  }

  const incidentAt = new Date(incidentLocal);
  if (Number.isNaN(incidentAt.getTime())) {
    return { ok: false, error: "The incident date could not be read." };
  }
  if (incidentAt.getTime() > Date.now()) {
    return { ok: false, error: "An incident cannot be reported before it happens." };
  }

  const result = await apiTry<Complaint>("/complaints", {
    method: "POST",
    body: {
      hospital_id: hospitalId,
      incident_at: incidentAt.toISOString(),
      category: String(formData.get("category") ?? ""),
      description: String(formData.get("description") ?? "").trim(),
      evidence: evidence.map((attachment) => ({
        url: attachment.url,
        evidence_type: attachment.evidence_type,
        content_type: attachment.content_type,
        file_name: attachment.file_name,
        size_bytes: attachment.size_bytes,
        checksum_sha256: attachment.checksum_sha256,
      })),
    },
  });

  if (!result.ok) return { ok: false, error: result.error };

  revalidatePath("/citizen/complaints");
  return { ok: true, complaintNumber: result.data.complaint_number };
}
