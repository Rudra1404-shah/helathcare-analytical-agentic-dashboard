"use client";

import { ShieldCheck } from "lucide-react";
import { useState } from "react";

import { updateAccreditation } from "@/app/(gov)/gov/actions";
import { AccreditationBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { FormDialog } from "@/components/ui/dialog";
import { Field, Select, Textarea } from "@/components/ui/field";
import { TD, TDMeta, TDPrimary, TR } from "@/components/ui/table";
import { useToast } from "@/components/ui/toast";
import type { AccreditationStatus, Hospital } from "@/lib/types";

const OPTIONS: { value: AccreditationStatus; label: string; consequence: string }[] = [
  { value: "NABH", label: "NABH accredited", consequence: "Highest national accreditation." },
  {
    value: "STATE_LICENSED",
    label: "State licensed",
    consequence: "Licensed to operate by the state authority.",
  },
  {
    value: "PENDING",
    label: "Pending",
    consequence: "Under review. The hospital continues to operate.",
  },
  {
    value: "BLACKLISTED",
    label: "Blacklisted",
    consequence:
      "Deactivates the hospital. It stops appearing anywhere a citizen or another hospital would choose one.",
  },
];

export function HospitalRow({ hospital }: { hospital: Hospital }) {
  return (
    <TR>
      <TDPrimary>
        {hospital.name}
        <TDMeta>{hospital.license_no}</TDMeta>
      </TDPrimary>
      <TD>
        {hospital.city}
        <TDMeta>
          {hospital.state} · {hospital.zone_code}
        </TDMeta>
      </TD>
      <TD>
        <span className="text-sm">
          {hospital.sector_type.charAt(0) + hospital.sector_type.slice(1).toLowerCase()}
        </span>
      </TD>
      <TD numeric>{hospital.capacity.total_sanctioned_beds}</TD>
      <TD numeric>{hospital.capacity.icu_beds}</TD>
      <TD>
        <AccreditationBadge status={hospital.accreditation_status} />
      </TD>
      <TD className="text-right">
        <AccreditationDialog hospital={hospital} />
      </TD>
    </TR>
  );
}

function AccreditationDialog({ hospital }: { hospital: Hospital }) {
  const [status, setStatus] = useState<AccreditationStatus>(hospital.accreditation_status);
  const { confirm } = useToast();

  const chosen = OPTIONS.find((option) => option.value === status);
  const blacklisting = status === "BLACKLISTED";

  return (
    <FormDialog
      trigger={
        <Button variant="ghost" size="sm">
          <ShieldCheck strokeWidth={1.75} aria-hidden="true" />
          Change
        </Button>
      }
      title="Accreditation decision"
      description={`${hospital.name} · ${hospital.license_no}`}
      submitLabel={blacklisting ? "Blacklist hospital" : "Save decision"}
      submitVariant={blacklisting ? "destructive" : "primary"}
      action={(formData) => updateAccreditation(hospital._id, formData)}
      onSuccess={() => confirm(`Accreditation updated for ${hospital.name}.`)}
    >
      {({ pending }) => (
        <>
          <Field label="Accreditation status" htmlFor="accreditation_status" required>
            <Select
              id="accreditation_status"
              name="accreditation_status"
              value={status}
              onChange={(event) => setStatus(event.target.value as AccreditationStatus)}
              disabled={pending}
            >
              {OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </Select>
          </Field>

          {chosen ? (
            <p
              className={
                blacklisting
                  ? "rounded-md bg-critical-muted px-3 py-2 text-sm text-critical"
                  : "text-sm text-muted-foreground"
              }
            >
              {chosen.consequence}
            </p>
          ) : null}

          <Field
            label="Closure remarks"
            htmlFor="remarks"
            hint="Recorded against your account in the audit trail."
            required
          >
            <Textarea
              id="remarks"
              name="remarks"
              required
              disabled={pending}
              placeholder="Repeated hygiene violations confirmed on inspection of 14 August."
            />
          </Field>
        </>
      )}
    </FormDialog>
  );
}
