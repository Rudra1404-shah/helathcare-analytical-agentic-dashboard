"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { Loader2, ShieldCheck } from "lucide-react";
import { useState, useTransition } from "react";

import { updateAccreditation } from "@/app/(gov)/gov/actions";
import { AccreditationBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Field, Select, Textarea } from "@/components/ui/field";
import { TD, TDMeta, TDPrimary, TR } from "@/components/ui/table";
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
  const [open, setOpen] = useState(false);
  const [status, setStatus] = useState<AccreditationStatus>(hospital.accreditation_status);
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    const formData = new FormData(event.currentTarget);

    startTransition(async () => {
      const result = await updateAccreditation(hospital._id, formData);
      if (result.ok) {
        setOpen(false);
      } else {
        setError(result.error ?? "The change could not be saved.");
      }
    });
  }

  const chosen = OPTIONS.find((option) => option.value === status);
  const blacklisting = status === "BLACKLISTED";

  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <Dialog.Trigger asChild>
        <Button variant="ghost" size="sm">
          <ShieldCheck strokeWidth={1.75} aria-hidden="true" />
          Change
        </Button>
      </Dialog.Trigger>

      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-slate-950/40" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-[min(32rem,calc(100vw-2rem))] -translate-x-1/2 -translate-y-1/2 rounded-lg border border-border bg-surface p-5 shadow-lg">
          <Dialog.Title className="text-sm font-semibold text-foreground">
            Accreditation decision
          </Dialog.Title>
          <Dialog.Description className="mt-1 text-sm text-muted-foreground">
            {hospital.name} · {hospital.license_no}
          </Dialog.Description>

          <form onSubmit={handleSubmit} className="mt-4 flex flex-col gap-4">
            <Field label="Accreditation status" htmlFor="accreditation_status" required>
              <Select
                id="accreditation_status"
                name="accreditation_status"
                value={status}
                onChange={(event) =>
                  setStatus(event.target.value as AccreditationStatus)
                }
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

            {error ? (
              <p
                role="alert"
                className="rounded-md bg-critical-muted px-3 py-2 text-sm text-critical"
              >
                {error}
              </p>
            ) : null}

            <div className="flex justify-end gap-2">
              <Dialog.Close asChild>
                <Button type="button" variant="secondary" disabled={pending}>
                  Cancel
                </Button>
              </Dialog.Close>
              <Button
                type="submit"
                variant={blacklisting ? "destructive" : "primary"}
                disabled={pending}
              >
                {pending ? (
                  <>
                    <Loader2 className="animate-spin" strokeWidth={1.75} aria-hidden="true" />
                    Saving
                  </>
                ) : blacklisting ? (
                  "Blacklist hospital"
                ) : (
                  "Save decision"
                )}
              </Button>
            </div>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
