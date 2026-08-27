"use server";

import { revalidatePath } from "next/cache";

import { apiTry } from "@/lib/api";
import type { Patient } from "@/lib/types";

/**
 * Hospital write actions.
 *
 * These run on the server, so the session token stays in the httpOnly cookie.
 * Errors come back as the API's own message, which is written for a human and
 * usually names the exact field at fault.
 */

export interface IntakeResult {
  ok: boolean;
  mrn?: string;
  error?: string;
}

/** Split a comma-separated field into a clean list. */
function list(value: FormDataEntryValue | null): string[] {
  return String(value ?? "")
    .split(",")
    .map((entry) => entry.trim())
    .filter(Boolean);
}

function optional(value: FormDataEntryValue | null): string | undefined {
  const text = String(value ?? "").trim();
  return text === "" ? undefined : text;
}

export async function intakePatient(
  hospitalId: string,
  formData: FormData,
): Promise<IntakeResult> {
  const ageRaw = optional(formData.get("age_years"));
  const dateOfBirth = optional(formData.get("date_of_birth"));

  // Mirror the model's rule here, so the desk sees the problem before the
  // round trip: a record with neither signal cannot be triaged, because
  // paediatric and geriatric protocols differ sharply.
  if (!ageRaw && !dateOfBirth) {
    return {
      ok: false,
      error: "Give either an age or a date of birth. A record with neither cannot be triaged.",
    };
  }

  const result = await apiTry<Patient>(`/hospitals/${hospitalId}/patients`, {
    method: "POST",
    body: {
      mrn: String(formData.get("mrn") ?? "").trim(),
      full_name: String(formData.get("full_name") ?? "").trim(),
      gender: String(formData.get("gender") ?? "UNDISCLOSED"),
      age_years: ageRaw ? Number(ageRaw) : undefined,
      date_of_birth: dateOfBirth,
      phone: optional(formData.get("phone")),
      blood_group: optional(formData.get("blood_group")) ?? "UNKNOWN",
      national_id: optional(formData.get("national_id")),
      allergies: list(formData.get("allergies")),
      pre_existing_conditions: list(formData.get("pre_existing_conditions")),
    },
  });

  if (!result.ok) return { ok: false, error: result.error };

  revalidatePath("/hospital/patients");
  return { ok: true, mrn: result.data.mrn };
}
