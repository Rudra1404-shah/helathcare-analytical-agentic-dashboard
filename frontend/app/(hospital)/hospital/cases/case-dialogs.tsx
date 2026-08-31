"use client";

import { ArrowRightLeft, HeartPulse, LogOut, Plus } from "lucide-react";
import { useState } from "react";

import {
  admitPatient,
  dischargeCase,
  recordVitals,
  updateCaseStatus,
} from "@/app/(hospital)/hospital/actions";
import { Button } from "@/components/ui/button";
import { FormDialog } from "@/components/ui/dialog";
import { Field, Input, Select, Textarea } from "@/components/ui/field";
import { useToast } from "@/components/ui/toast";
import type { CaseStatus, CaseType, Department, Doctor, Patient } from "@/lib/types";

/**
 * The write flows for the ward.
 *
 * Every selector is populated from data the page already loaded on the server,
 * so opening a dialog costs no request and works the moment it appears. A
 * dialog that spins before it can be used is a dialog a nurse abandons.
 */

const OPEN_STATUSES: { value: CaseStatus; label: string; note: string }[] = [
  { value: "ADMITTED", label: "Admitted", note: "General ward." },
  { value: "ICU", label: "ICU", note: "Draws from the ICU bed pool." },
  { value: "OBSERVATION", label: "Observation", note: "Short stay, not yet admitted." },
];

const TRIAGE_OPTIONS = [
  { value: "1", label: "1 - Immediate" },
  { value: "2", label: "2 - Urgent" },
  { value: "3", label: "3 - Standard" },
  { value: "4", label: "4 - Non-urgent" },
];

const NUMERIC = "font-mono tabular-nums";

/** The five readings that make an observation set, laid out to be filled in order. */
function VitalsFields({
  prefix = "",
  disabled,
  required,
}: {
  prefix?: string;
  disabled: boolean;
  required?: boolean;
}) {
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
      <Field label="Systolic BP" htmlFor={prefix + "systolic_bp"} required={required}>
        <Input
          id={prefix + "systolic_bp"}
          name={prefix + "systolic_bp"}
          type="number"
          min={40}
          max={300}
          inputMode="numeric"
          className={NUMERIC}
          disabled={disabled}
          required={required}
          placeholder="120"
        />
      </Field>
      <Field label="Diastolic BP" htmlFor={prefix + "diastolic_bp"} required={required}>
        <Input
          id={prefix + "diastolic_bp"}
          name={prefix + "diastolic_bp"}
          type="number"
          min={20}
          max={200}
          inputMode="numeric"
          className={NUMERIC}
          disabled={disabled}
          required={required}
          placeholder="80"
        />
      </Field>
      <Field label="Pulse (bpm)" htmlFor={prefix + "pulse_bpm"} required={required}>
        <Input
          id={prefix + "pulse_bpm"}
          name={prefix + "pulse_bpm"}
          type="number"
          min={20}
          max={300}
          inputMode="numeric"
          className={NUMERIC}
          disabled={disabled}
          required={required}
          placeholder="72"
        />
      </Field>
      <Field label="SpO2 (%)" htmlFor={prefix + "spo2_percent"} required={required}>
        <Input
          id={prefix + "spo2_percent"}
          name={prefix + "spo2_percent"}
          type="number"
          min={0}
          max={100}
          step="0.1"
          inputMode="decimal"
          className={NUMERIC}
          disabled={disabled}
          required={required}
          placeholder="98"
        />
      </Field>
      <Field
        label="Temperature (C)"
        htmlFor={prefix + "temperature_celsius"}
        required={required}
      >
        <Input
          id={prefix + "temperature_celsius"}
          name={prefix + "temperature_celsius"}
          type="number"
          min={25}
          max={45}
          step="0.1"
          inputMode="decimal"
          className={NUMERIC}
          disabled={disabled}
          required={required}
          placeholder="36.8"
        />
      </Field>
      <Field label="Resp. rate" htmlFor={prefix + "respiratory_rate"} hint="Optional">
        <Input
          id={prefix + "respiratory_rate"}
          name={prefix + "respiratory_rate"}
          type="number"
          min={4}
          max={80}
          inputMode="numeric"
          className={NUMERIC}
          disabled={disabled}
          placeholder="16"
        />
      </Field>
    </div>
  );
}

// --------------------------------------------------------------------------
// Admit
// --------------------------------------------------------------------------

export function AdmitCaseDialog({
  hospitalId,
  suggestedCaseNumber,
  patients,
  doctors,
  departments,
  caseTypes,
}: {
  hospitalId: string;
  suggestedCaseNumber: string;
  patients: Patient[];
  doctors: Doctor[];
  departments: Department[];
  caseTypes: CaseType[];
}) {
  const { confirm } = useToast();

  // Admission needs a patient, a doctor, and a department. Naming the one that
  // is missing beats a disabled button that explains nothing.
  const missing = [
    patients.length === 0 ? "a registered patient" : null,
    doctors.length === 0 ? "an onboarded doctor" : null,
    departments.length === 0 ? "a department" : null,
  ].filter(Boolean);

  if (missing.length > 0) {
    return (
      <Button size="sm" disabled title={"Admission needs " + missing.join(", ") + "."}>
        <Plus strokeWidth={1.75} aria-hidden="true" />
        Admit patient
      </Button>
    );
  }

  return (
    <FormDialog
      size="lg"
      trigger={
        <Button size="sm">
          <Plus strokeWidth={1.75} aria-hidden="true" />
          Admit patient
        </Button>
      }
      title="Admit a patient"
      description="Opens a case and reserves a bed from the matching inventory pool."
      submitLabel="Admit patient"
      pendingLabel="Admitting"
      action={(formData) => admitPatient(hospitalId, formData)}
      onSuccess={() => confirm("Case opened.")}
    >
      {({ pending }) => (
        <>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Patient" htmlFor="patient_id" required>
              <Select id="patient_id" name="patient_id" required disabled={pending}>
                {patients.map((patient) => (
                  <option key={patient._id} value={patient._id}>
                    {patient.full_name} - {patient.mrn}
                  </option>
                ))}
              </Select>
            </Field>

            <Field
              label="Case number"
              htmlFor="case_number"
              hint="Unique within this hospital."
              required
            >
              <Input
                id="case_number"
                name="case_number"
                required
                minLength={3}
                maxLength={40}
                defaultValue={suggestedCaseNumber}
                className={NUMERIC}
                disabled={pending}
              />
            </Field>

            <Field label="Attending doctor" htmlFor="doctor_id" required>
              <Select id="doctor_id" name="doctor_id" required disabled={pending}>
                {doctors.map((doctor) => (
                  <option key={doctor._id} value={doctor._id}>
                    {doctor.full_name} - {doctor.specialization}
                  </option>
                ))}
              </Select>
            </Field>

            <Field label="Department" htmlFor="department_id" required>
              <Select id="department_id" name="department_id" required disabled={pending}>
                {departments.map((department) => (
                  <option key={department._id} value={department._id}>
                    {department.name}
                  </option>
                ))}
              </Select>
            </Field>

            <Field
              label="Case type"
              htmlFor="case_type_id"
              hint="Optional. Sets the default triage."
            >
              <Select id="case_type_id" name="case_type_id" disabled={pending}>
                <option value="">Not yet classified</option>
                {caseTypes.map((caseType) => (
                  <option key={caseType._id} value={caseType._id}>
                    {caseType.name}
                  </option>
                ))}
              </Select>
            </Field>

            <Field label="Triage level" htmlFor="triage_level" hint="Overrides the case type.">
              <Select id="triage_level" name="triage_level" disabled={pending}>
                <option value="">From case type</option>
                {TRIAGE_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </Select>
            </Field>

            <Field label="Ward" htmlFor="status" required>
              <Select id="status" name="status" defaultValue="ADMITTED" disabled={pending}>
                {OPEN_STATUSES.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </Select>
            </Field>

            <Field label="Bed" htmlFor="bed_allocated" hint="For example GW-14 or ICU-3.">
              <Input
                id="bed_allocated"
                name="bed_allocated"
                maxLength={40}
                className="font-mono"
                disabled={pending}
                placeholder="GW-14"
              />
            </Field>
          </div>

          <Field
            label="Chief symptoms"
            htmlFor="chief_symptoms"
            hint="Separate with commas."
            required
          >
            <Input
              id="chief_symptoms"
              name="chief_symptoms"
              required
              disabled={pending}
              placeholder="Fever, Cough, Breathlessness"
            />
          </Field>

          <fieldset className="rounded-md border border-border p-3">
            <legend className="px-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Initial observations
            </legend>
            <p className="mb-3 text-xs text-muted-foreground">
              Optional at the desk. Record all five or none, so the first reading can be
              compared against the next one.
            </p>
            <VitalsFields prefix="initial_" disabled={pending} />
          </fieldset>
        </>
      )}
    </FormDialog>
  );
}

// --------------------------------------------------------------------------
// Per-case actions
// --------------------------------------------------------------------------

export function RecordVitalsDialog({
  caseId,
  caseNumber,
  compact,
}: {
  caseId: string;
  caseNumber: string;
  compact?: boolean;
}) {
  const { confirm } = useToast();

  return (
    <FormDialog
      trigger={
        <Button variant="ghost" size="sm">
          <HeartPulse strokeWidth={1.75} aria-hidden="true" />
          {compact ? "Vitals" : "Record vitals"}
        </Button>
      }
      title="Record observations"
      description={"Case " + caseNumber}
      submitLabel="Save observations"
      action={(formData) => recordVitals(caseId, formData)}
      onSuccess={() => confirm("Observations recorded for " + caseNumber + ".")}
    >
      {({ pending }) => <VitalsFields disabled={pending} required />}
    </FormDialog>
  );
}

export function TransferCaseDialog({
  caseId,
  caseNumber,
  currentStatus,
  currentBed,
}: {
  caseId: string;
  caseNumber: string;
  currentStatus: CaseStatus;
  currentBed: string | null;
}) {
  const { confirm } = useToast();
  const [status, setStatus] = useState<CaseStatus>(currentStatus);
  const chosen = OPEN_STATUSES.find((option) => option.value === status);

  return (
    <FormDialog
      trigger={
        <Button variant="ghost" size="sm">
          <ArrowRightLeft strokeWidth={1.75} aria-hidden="true" />
          Transfer
        </Button>
      }
      title="Transfer ward"
      description={"Case " + caseNumber}
      submitLabel="Save transfer"
      action={(formData) => updateCaseStatus(caseId, formData)}
      onSuccess={() => confirm(caseNumber + " moved to " + status.toLowerCase() + ".")}
    >
      {({ pending }) => (
        <>
          <Field label="Ward" htmlFor="status" required>
            <Select
              id="status"
              name="status"
              value={status}
              onChange={(event) => setStatus(event.target.value as CaseStatus)}
              disabled={pending}
            >
              {OPEN_STATUSES.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </Select>
          </Field>

          {chosen ? <p className="text-sm text-muted-foreground">{chosen.note}</p> : null}

          <Field label="Bed" htmlFor="bed_allocated" hint="Leave as is to keep the current bed.">
            <Input
              id="bed_allocated"
              name="bed_allocated"
              maxLength={40}
              defaultValue={currentBed ?? ""}
              className="font-mono"
              disabled={pending}
              placeholder="ICU-3"
            />
          </Field>
        </>
      )}
    </FormDialog>
  );
}

export function DischargeCaseDialog({
  caseId,
  caseNumber,
}: {
  caseId: string;
  caseNumber: string;
}) {
  const { confirm } = useToast();
  const [status, setStatus] = useState<"DISCHARGED" | "DECEASED">("DISCHARGED");
  const died = status === "DECEASED";

  return (
    <FormDialog
      trigger={
        <Button variant="ghost" size="sm">
          <LogOut strokeWidth={1.75} aria-hidden="true" />
          Discharge
        </Button>
      }
      title="Close this case"
      description={"Case " + caseNumber}
      submitLabel={died ? "Record death" : "Discharge patient"}
      submitVariant={died ? "destructive" : "primary"}
      pendingLabel="Closing"
      action={(formData) => dischargeCase(caseId, formData)}
      onSuccess={() =>
        confirm(
          died ? caseNumber + " closed as deceased." : caseNumber + " discharged.",
        )
      }
    >
      {({ pending }) => (
        <>
          <Field label="Outcome" htmlFor="status" required>
            <Select
              id="status"
              name="status"
              value={status}
              onChange={(event) => setStatus(event.target.value as "DISCHARGED" | "DECEASED")}
              disabled={pending}
            >
              <option value="DISCHARGED">Discharged</option>
              <option value="DECEASED">Deceased</option>
            </Select>
          </Field>

          {died ? (
            <p className="rounded-md bg-critical-muted px-3 py-2 text-sm text-critical">
              This closes the case as a death in care. It is reportable and cannot be
              reopened from this screen.
            </p>
          ) : null}

          <Field
            label="Discharge summary"
            htmlFor="discharge_summary"
            hint="Follows the patient to their next admission at any hospital."
            required
          >
            <Textarea
              id="discharge_summary"
              name="discharge_summary"
              required
              disabled={pending}
              placeholder="Community-acquired pneumonia. Treated with IV antibiotics, afebrile 48 hours. Advised follow-up in one week."
            />
          </Field>
        </>
      )}
    </FormDialog>
  );
}

/** The action set for one case. A closed case keeps only its observation history. */
export function CaseActions({
  caseId,
  caseNumber,
  status,
  bed,
  compact,
}: {
  caseId: string;
  caseNumber: string;
  status: CaseStatus;
  bed: string | null;
  compact?: boolean;
}) {
  const closed = status === "DISCHARGED" || status === "DECEASED";

  if (closed) {
    return <span className="text-xs text-muted-foreground">Closed</span>;
  }

  return (
    <div className="flex flex-wrap items-center justify-end gap-1">
      <RecordVitalsDialog caseId={caseId} caseNumber={caseNumber} compact={compact} />
      <TransferCaseDialog
        caseId={caseId}
        caseNumber={caseNumber}
        currentStatus={status}
        currentBed={bed}
      />
      <DischargeCaseDialog caseId={caseId} caseNumber={caseNumber} />
    </div>
  );
}
