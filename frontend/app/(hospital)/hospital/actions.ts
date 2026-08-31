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

// --------------------------------------------------------------------------
// Cases and triage
// --------------------------------------------------------------------------

export interface ActionResult {
  ok: boolean;
  error?: string;
}

/** Read a required integer field, rejecting the empty string rather than coercing it to 0. */
function requiredNumber(value: FormDataEntryValue | null): number | null {
  const text = String(value ?? "").trim();
  if (text === "") return null;
  const parsed = Number(text);
  return Number.isFinite(parsed) ? parsed : null;
}

function optionalNumber(value: FormDataEntryValue | null): number | undefined {
  const parsed = requiredNumber(value);
  return parsed === null ? undefined : parsed;
}

/**
 * Collect an observation set from a form.
 *
 * Returns `undefined` when nothing was filled in, which is how the admission
 * form says "no vitals taken at the desk" without sending a half-empty set the
 * API would rightly reject.
 */
function vitalsFrom(
  formData: FormData,
  prefix = "",
): { body?: Record<string, number>; error?: string } {
  const fields = {
    systolic_bp: requiredNumber(formData.get(`${prefix}systolic_bp`)),
    diastolic_bp: requiredNumber(formData.get(`${prefix}diastolic_bp`)),
    pulse_bpm: requiredNumber(formData.get(`${prefix}pulse_bpm`)),
    spo2_percent: requiredNumber(formData.get(`${prefix}spo2_percent`)),
    temperature_celsius: requiredNumber(formData.get(`${prefix}temperature_celsius`)),
  };

  const supplied = Object.values(fields).filter((value) => value !== null);
  if (supplied.length === 0) return {};

  if (supplied.length < 5) {
    return {
      error:
        "Record the full observation set. A partial set cannot be compared against the previous reading, which is the only thing that shows deterioration.",
    };
  }

  const body = fields as Record<string, number>;
  const respiratory = optionalNumber(formData.get(`${prefix}respiratory_rate`));
  if (respiratory !== undefined) body.respiratory_rate = respiratory;

  return { body };
}

export async function admitPatient(
  hospitalId: string,
  formData: FormData,
): Promise<ActionResult> {
  const symptoms = list(formData.get("chief_symptoms"));
  if (symptoms.length === 0) {
    return {
      ok: false,
      error: "Record at least one presenting symptom. A case with none cannot be triaged.",
    };
  }

  const vitals = vitalsFrom(formData, "initial_");
  if (vitals.error) return { ok: false, error: vitals.error };

  const triage = optionalNumber(formData.get("triage_level"));

  const result = await apiTry(`/hospitals/${hospitalId}/cases`, {
    method: "POST",
    body: {
      case_number: String(formData.get("case_number") ?? "").trim(),
      patient_id: String(formData.get("patient_id") ?? ""),
      doctor_id: String(formData.get("doctor_id") ?? ""),
      department_id: String(formData.get("department_id") ?? ""),
      case_type_id: optional(formData.get("case_type_id")),
      bed_allocated: optional(formData.get("bed_allocated")),
      triage_level: triage,
      chief_symptoms: symptoms,
      initial_vitals: vitals.body,
      status: String(formData.get("status") ?? "ADMITTED"),
    },
  });

  if (!result.ok) return { ok: false, error: result.error };

  revalidatePath("/hospital/cases");
  revalidatePath("/hospital");
  return { ok: true };
}

export async function recordVitals(caseId: string, formData: FormData): Promise<ActionResult> {
  const vitals = vitalsFrom(formData);
  if (vitals.error) return { ok: false, error: vitals.error };
  if (!vitals.body) {
    return { ok: false, error: "Enter the observation set before saving." };
  }

  const result = await apiTry(`/cases/${caseId}/vitals`, {
    method: "POST",
    body: vitals.body,
  });

  if (!result.ok) return { ok: false, error: result.error };

  revalidatePath("/hospital/cases");
  return { ok: true };
}

export async function dischargeCase(caseId: string, formData: FormData): Promise<ActionResult> {
  const status = String(formData.get("status") ?? "");
  const summary = String(formData.get("discharge_summary") ?? "").trim();

  if (status !== "DISCHARGED" && status !== "DECEASED") {
    return { ok: false, error: "Choose how the case closed." };
  }
  // Mirrored from the API so the ward sees it before the round trip. The
  // summary is what the next hospital reads when this patient presents again.
  if (!summary) {
    return {
      ok: false,
      error:
        "Write a discharge summary. It is the only clinical record that follows the patient to their next admission.",
    };
  }

  const result = await apiTry(`/cases/${caseId}/discharge`, {
    method: "POST",
    body: { status, discharge_summary: summary },
  });

  if (!result.ok) return { ok: false, error: result.error };

  revalidatePath("/hospital/cases");
  revalidatePath("/hospital");
  return { ok: true };
}

export async function updateCaseStatus(
  caseId: string,
  formData: FormData,
): Promise<ActionResult> {
  const status = optional(formData.get("status"));
  const bed = optional(formData.get("bed_allocated"));

  if (!status && !bed) {
    return { ok: false, error: "Change the ward or the bed before saving." };
  }

  const result = await apiTry(`/cases/${caseId}`, {
    method: "PATCH",
    body: { status, bed_allocated: bed },
  });

  if (!result.ok) return { ok: false, error: result.error };

  revalidatePath("/hospital/cases");
  revalidatePath("/hospital");
  return { ok: true };
}

// --------------------------------------------------------------------------
// Inventory
// --------------------------------------------------------------------------

export async function addInventoryItem(
  hospitalId: string,
  formData: FormData,
): Promise<ActionResult> {
  const total = requiredNumber(formData.get("total_stock"));
  const available = requiredNumber(formData.get("available_stock"));
  const threshold = requiredNumber(formData.get("min_safety_threshold")) ?? 0;

  if (total === null || available === null) {
    return { ok: false, error: "Enter both the total stock and how much of it is free." };
  }
  // Mirrored from the model. Stock that is free cannot exceed stock that
  // exists, and a capacity view built on that contradiction is worthless.
  if (available > total) {
    return {
      ok: false,
      error: `Available stock (${available}) cannot exceed total stock (${total}).`,
    };
  }

  const result = await apiTry(`/hospitals/${hospitalId}/inventory`, {
    method: "POST",
    body: {
      category: String(formData.get("category") ?? ""),
      item_name: String(formData.get("item_name") ?? "").trim(),
      total_stock: total,
      available_stock: available,
      min_safety_threshold: threshold,
      unit: String(formData.get("unit") ?? "UNITS"),
      expires_on: optional(formData.get("expires_on")),
    },
  });

  if (!result.ok) return { ok: false, error: result.error };

  revalidatePath("/hospital/inventory");
  revalidatePath("/hospital");
  return { ok: true };
}

/**
 * Move stock.
 *
 * The two directions are genuinely different operations, not a sign flip.
 *
 * Consuming or writing off reduces what is available while the sanctioned
 * total stays the same, which is exactly what `/adjust` does, and it records a
 * reason in the ledger.
 *
 * Receiving a delivery raises both the total and the available figure. `/adjust`
 * cannot express that: its delta moves available stock alone, so using it here
 * would push available above total and the model would rightly refuse. That
 * path therefore goes through PATCH, which can move both in one write.
 *
 * The cost is that a receipt is a read-modify-write on figures the form was
 * rendered with: two desks receiving the same line at the same moment would
 * have the later write win. Consumption, the far more frequent operation, stays
 * on the atomic endpoint.
 */
export async function adjustStock(itemId: string, formData: FormData): Promise<ActionResult> {
  const magnitude = requiredNumber(formData.get("quantity"));
  const direction = String(formData.get("direction") ?? "receive");
  const reason = String(formData.get("reason") ?? "").trim();

  if (magnitude === null || magnitude <= 0) {
    return { ok: false, error: "Enter how much stock is moving. It has to be more than zero." };
  }
  if (!reason) {
    return { ok: false, error: "Record why the stock moved. The ledger is audited." };
  }

  if (direction === "receive") {
    const total = requiredNumber(formData.get("current_total"));
    const available = requiredNumber(formData.get("current_available"));
    if (total === null || available === null) {
      return { ok: false, error: "The current stock figures could not be read. Reload and retry." };
    }

    const result = await apiTry(`/inventory/${itemId}`, {
      method: "PATCH",
      body: {
        total_stock: total + magnitude,
        available_stock: available + magnitude,
        last_restocked_at: new Date().toISOString(),
      },
    });

    if (!result.ok) return { ok: false, error: result.error };
  } else {
    const result = await apiTry(`/inventory/${itemId}/adjust`, {
      method: "POST",
      body: { delta: -magnitude, reason },
    });

    if (!result.ok) return { ok: false, error: result.error };
  }

  revalidatePath("/hospital/inventory");
  revalidatePath("/hospital");
  return { ok: true };
}

export async function updateInventoryItem(
  itemId: string,
  formData: FormData,
): Promise<ActionResult> {
  const threshold = requiredNumber(formData.get("min_safety_threshold"));
  const total = optionalNumber(formData.get("total_stock"));
  const expires = optional(formData.get("expires_on"));

  if (threshold === null) {
    return { ok: false, error: "Enter the safety threshold." };
  }

  const result = await apiTry(`/inventory/${itemId}`, {
    method: "PATCH",
    body: {
      min_safety_threshold: threshold,
      total_stock: total,
      expires_on: expires,
    },
  });

  if (!result.ok) return { ok: false, error: result.error };

  revalidatePath("/hospital/inventory");
  revalidatePath("/hospital");
  return { ok: true };
}

// --------------------------------------------------------------------------
// Workforce
// --------------------------------------------------------------------------

/** Roles the API treats as clinical. These post to a different endpoint. */
const MEDICAL_ROLES = new Set([
  "STAFF_NURSE",
  "MATRON",
  "LAB_ASSISTANT",
  "WARD_BOY",
  "COMPOUNDER",
]);

export async function onboardDoctor(
  hospitalId: string,
  formData: FormData,
): Promise<ActionResult> {
  const shifts = formData.getAll("shifts").map(String).filter(Boolean);
  if (shifts.length === 0) {
    return {
      ok: false,
      error: "Assign at least one shift. A doctor on no shift can never be put on a rota.",
    };
  }

  const result = await apiTry(`/hospitals/${hospitalId}/doctors`, {
    method: "POST",
    body: {
      full_name: String(formData.get("full_name") ?? "").trim(),
      license_no: String(formData.get("license_no") ?? "").trim(),
      specialization: String(formData.get("specialization") ?? "").trim(),
      department_id: String(formData.get("department_id") ?? ""),
      qualification: String(formData.get("qualification") ?? "").trim(),
      phone: optional(formData.get("phone")),
      email: optional(formData.get("email")),
      employment_type: String(formData.get("employment_type") ?? "FULL_TIME"),
      shifts,
      max_daily_patients: optionalNumber(formData.get("max_daily_patients")) ?? 30,
      is_emergency_on_call: formData.get("is_emergency_on_call") === "on",
    },
  });

  if (!result.ok) return { ok: false, error: result.error };

  revalidatePath("/hospital/doctors");
  return { ok: true };
}

/**
 * Register a staff member.
 *
 * Clinical and support staff are two endpoints, not one with a flag: only the
 * clinical intake accepts a council registration number, and the API refuses
 * one on a cleaner. The role chosen here decides which is called.
 */
export async function intakeStaff(
  hospitalId: string,
  formData: FormData,
): Promise<ActionResult> {
  const role = String(formData.get("role") ?? "");
  if (!role) return { ok: false, error: "Choose a role." };

  const medical = MEDICAL_ROLES.has(role);
  const registration = String(formData.get("registration_no") ?? "").trim();

  if (medical && !registration) {
    return {
      ok: false,
      error:
        "Clinical staff need a council registration number. It is what ties this person to a regulator.",
    };
  }

  const body: Record<string, unknown> = {
    full_name: String(formData.get("full_name") ?? "").trim(),
    employee_id: String(formData.get("employee_id") ?? "").trim(),
    phone: String(formData.get("phone") ?? "").trim(),
    department_id: optional(formData.get("department_id")),
    assigned_ward_area: optional(formData.get("assigned_ward_area")),
    shift: String(formData.get("shift") ?? "GENERAL"),
    role,
  };

  if (medical) {
    body.registration_no = registration;
    body.is_emergency_on_call = formData.get("is_emergency_on_call") === "on";
  }

  const endpoint = medical ? "medical" : "admin-support";
  const result = await apiTry(`/hospitals/${hospitalId}/staff/${endpoint}`, {
    method: "POST",
    body,
  });

  if (!result.ok) return { ok: false, error: result.error };

  revalidatePath("/hospital/staff");
  return { ok: true };
}

export async function createDepartment(
  hospitalId: string,
  formData: FormData,
): Promise<ActionResult> {
  const result = await apiTry(`/hospitals/${hospitalId}/departments`, {
    method: "POST",
    body: {
      name: String(formData.get("name") ?? "").trim(),
      code: String(formData.get("code") ?? "").trim().toUpperCase(),
      floor: optional(formData.get("floor")),
      wing: optional(formData.get("wing")),
      hod_doctor_id: optional(formData.get("hod_doctor_id")),
      bed_count: optionalNumber(formData.get("bed_count")) ?? 0,
    },
  });

  if (!result.ok) return { ok: false, error: result.error };

  revalidatePath("/hospital/departments");
  return { ok: true };
}

// --------------------------------------------------------------------------
// Billing
// --------------------------------------------------------------------------

/**
 * Raise an invoice.
 *
 * Money is forwarded as the **string** the cashier typed. The backend parses
 * it into a Decimal, which is the whole reason billing is not floats: a
 * rounding drift here becomes an Overcharging complaint later. Passing these
 * through `Number()` would undo that in one line.
 */
export async function createBill(
  hospitalId: string,
  formData: FormData,
): Promise<ActionResult> {
  const descriptions = formData.getAll("line_description").map(String);
  const rates = formData.getAll("line_rate").map(String);
  const quantities = formData.getAll("line_quantity").map(String);

  const lineItems = descriptions
    .map((description, index) => ({
      description: description.trim(),
      rate: (rates[index] ?? "").trim(),
      quantity: (quantities[index] ?? "").trim(),
    }))
    .filter((item) => item.description !== "" || item.rate !== "" || item.quantity !== "");

  if (lineItems.length === 0) {
    return { ok: false, error: "An invoice must charge for at least one thing." };
  }

  const incomplete = lineItems.findIndex(
    (item) => item.description === "" || item.rate === "" || item.quantity === "",
  );
  if (incomplete >= 0) {
    return {
      ok: false,
      error: `Line ${incomplete + 1} is missing a description, a rate, or a quantity.`,
    };
  }

  const result = await apiTry(`/hospitals/${hospitalId}/bills`, {
    method: "POST",
    body: {
      invoice_no: String(formData.get("invoice_no") ?? "").trim(),
      case_id: String(formData.get("case_id") ?? ""),
      patient_id: String(formData.get("patient_id") ?? ""),
      line_items: lineItems,
      tax_amount: String(formData.get("tax_amount") ?? "0.00").trim() || "0.00",
      discount_amount: String(formData.get("discount_amount") ?? "0.00").trim() || "0.00",
      payment_mode: optional(formData.get("payment_mode")),
    },
  });

  if (!result.ok) return { ok: false, error: result.error };

  revalidatePath("/hospital/bills");
  return { ok: true };
}

export async function recordPayment(
  billId: string,
  formData: FormData,
): Promise<ActionResult> {
  const amount = String(formData.get("amount") ?? "").trim();
  const mode = String(formData.get("payment_mode") ?? "");

  if (!amount) return { ok: false, error: "Enter the amount received." };
  if (!mode) return { ok: false, error: "Record how the payment was made." };

  const result = await apiTry(`/bills/${billId}/payments`, {
    method: "POST",
    body: {
      amount,
      payment_mode: mode,
      reference: optional(formData.get("reference")),
    },
  });

  if (!result.ok) return { ok: false, error: result.error };

  revalidatePath("/hospital/bills");
  revalidatePath(`/hospital/bills/${billId}`);
  return { ok: true };
}

// --------------------------------------------------------------------------
// Case types
// --------------------------------------------------------------------------

/**
 * Define a clinical protocol.
 *
 * A notifiable case type is reported to the ministry and watched for outbreak
 * clustering, so the flag is asked for explicitly rather than inferred from
 * the disease category.
 */
export async function createCaseType(formData: FormData): Promise<ActionResult> {
  const triage = requiredNumber(formData.get("triage_level"));
  if (triage === null) {
    return { ok: false, error: "Choose a default triage level." };
  }

  const result = await apiTry("/case-types", {
    method: "POST",
    body: {
      name: String(formData.get("name") ?? "").trim(),
      disease_category: String(formData.get("disease_category") ?? ""),
      icd10_code: String(formData.get("icd10_code") ?? "").trim().toUpperCase(),
      triage_level: triage,
      description: optional(formData.get("description")),
      is_notifiable: formData.get("is_notifiable") === "on",
    },
  });

  if (!result.ok) return { ok: false, error: result.error };

  revalidatePath("/hospital/case-types");
  revalidatePath("/hospital/cases");
  return { ok: true };
}
