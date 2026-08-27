"use server";

import { revalidatePath } from "next/cache";

import { apiTry } from "@/lib/api";
import type { AccreditationStatus, ActionTaken, InvestigationStatus } from "@/lib/types";

/**
 * Ministry write actions.
 *
 * These run on the server, so the session token stays in the httpOnly cookie
 * and never reaches the browser. Each returns the API's own error message when
 * a call fails, because the platform writes those messages for a human to read.
 */

export interface ActionResult {
  ok: boolean;
  error?: string;
}

export async function updateAccreditation(
  hospitalId: string,
  formData: FormData,
): Promise<ActionResult> {
  const status = String(formData.get("accreditation_status") ?? "") as AccreditationStatus;
  const remarks = String(formData.get("remarks") ?? "").trim();

  if (!status) {
    return { ok: false, error: "Choose an accreditation status." };
  }
  if (!remarks) {
    return {
      ok: false,
      error: "Record why this decision was made. An accreditation change with no rationale is not auditable.",
    };
  }

  const result = await apiTry(`/hospitals/${hospitalId}/accreditation`, {
    method: "PATCH",
    body: { accreditation_status: status, remarks },
  });

  if (!result.ok) return { ok: false, error: result.error };

  revalidatePath("/gov/hospitals");
  return { ok: true };
}

export async function updateInvestigation(
  complaintId: string,
  formData: FormData,
): Promise<ActionResult> {
  const status = String(
    formData.get("investigation_status") ?? "",
  ) as InvestigationStatus;

  if (!status) {
    return { ok: false, error: "Choose an investigation status." };
  }

  const closing = status === "ACTION_TAKEN" || status === "DISMISSED";
  const actionTaken = String(formData.get("action_taken") ?? "") as ActionTaken | "";
  const closureRemarks = String(formData.get("closure_remarks") ?? "").trim();
  const explanation = String(formData.get("hospital_explanation") ?? "").trim();

  // Mirror the API's rule here so the official sees the problem before the
  // round trip, rather than after it.
  if (closing && !actionTaken) {
    return { ok: false, error: "Closing an investigation requires a recorded action." };
  }
  if (closing && !closureRemarks) {
    return {
      ok: false,
      error: "Closing an investigation requires closure remarks explaining the decision.",
    };
  }

  const result = await apiTry(`/complaints/${complaintId}/investigation`, {
    method: "PATCH",
    body: {
      investigation_status: status,
      action_taken: actionTaken || undefined,
      closure_remarks: closureRemarks || undefined,
      hospital_explanation: explanation || undefined,
    },
  });

  if (!result.ok) return { ok: false, error: result.error };

  revalidatePath("/gov/complaints");
  revalidatePath(`/gov/complaints/${complaintId}`);
  return { ok: true };
}
