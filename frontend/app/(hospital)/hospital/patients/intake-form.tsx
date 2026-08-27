"use client";

import { CheckCircle2, Loader2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useRef, useState, useTransition } from "react";

import { intakePatient } from "@/app/(hospital)/hospital/actions";
import { Button } from "@/components/ui/button";
import { Field, Input, Select } from "@/components/ui/field";
import { PanelBody, PanelHeader } from "@/components/ui/panel";
import type { Gender } from "@/lib/types";

const GENDERS: Gender[] = ["MALE", "FEMALE", "OTHER", "UNDISCLOSED"];
const BLOOD_GROUPS = ["UNKNOWN", "A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"];

export function IntakeForm({ hospitalId }: { hospitalId: string }) {
  const router = useRouter();
  const formRef = useRef<HTMLFormElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setSaved(null);
    const formData = new FormData(event.currentTarget);

    startTransition(async () => {
      const result = await intakePatient(hospitalId, formData);
      if (result.ok) {
        setSaved(result.mrn ?? null);
        formRef.current?.reset();
        router.refresh();
      } else {
        setError(result.error ?? "The patient could not be registered.");
      }
    });
  }

  return (
    <>
      <PanelHeader
        title="Patient intake"
        description="The Medical Record Number is unique within this hospital."
      />
      <PanelBody>
        <form ref={formRef} onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Medical Record Number" htmlFor="mrn" required>
              <Input id="mrn" name="mrn" required disabled={pending} className="font-mono" />
            </Field>

            <Field label="Full name" htmlFor="full_name" required>
              <Input id="full_name" name="full_name" required disabled={pending} />
            </Field>

            <Field label="Gender" htmlFor="gender" required>
              <Select id="gender" name="gender" required disabled={pending}>
                {GENDERS.map((gender) => (
                  <option key={gender} value={gender}>
                    {gender.charAt(0) + gender.slice(1).toLowerCase()}
                  </option>
                ))}
              </Select>
            </Field>

            <Field
              label="Age in years"
              htmlFor="age_years"
              hint="Or give a date of birth below."
            >
              <Input
                id="age_years"
                name="age_years"
                type="number"
                min={0}
                max={130}
                disabled={pending}
                className="font-mono"
              />
            </Field>

            <Field label="Date of birth" htmlFor="date_of_birth">
              <Input
                id="date_of_birth"
                name="date_of_birth"
                type="date"
                disabled={pending}
              />
            </Field>

            <Field label="Blood group" htmlFor="blood_group">
              <Select id="blood_group" name="blood_group" disabled={pending}>
                {BLOOD_GROUPS.map((group) => (
                  <option key={group} value={group}>
                    {group === "UNKNOWN" ? "Not known" : group}
                  </option>
                ))}
              </Select>
            </Field>

            <Field label="Phone" htmlFor="phone" hint="With country code, e.g. +919820012345">
              <Input id="phone" name="phone" type="tel" disabled={pending} />
            </Field>

            <Field
              label="National ID"
              htmlFor="national_id"
              hint="Encrypted before storage. Links this record to the citizen's unified history."
            >
              <Input id="national_id" name="national_id" disabled={pending} />
            </Field>
          </div>

          <Field
            label="Allergies"
            htmlFor="allergies"
            hint="Separate with commas."
          >
            <Input
              id="allergies"
              name="allergies"
              disabled={pending}
              placeholder="Penicillin, Sulfa drugs"
            />
          </Field>

          <Field
            label="Pre-existing conditions"
            htmlFor="pre_existing_conditions"
            hint="Separate with commas."
          >
            <Input
              id="pre_existing_conditions"
              name="pre_existing_conditions"
              disabled={pending}
              placeholder="Type 2 Diabetes, Hypertension"
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

          {saved ? (
            <p
              role="status"
              className="flex items-center gap-2 rounded-md bg-stable-muted px-3 py-2 text-sm text-stable"
            >
              <CheckCircle2 className="size-4 shrink-0" strokeWidth={1.75} aria-hidden="true" />
              Registered as <span className="font-mono">{saved}</span>.
            </p>
          ) : null}

          <Button type="submit" disabled={pending}>
            {pending ? (
              <>
                <Loader2 className="animate-spin" strokeWidth={1.75} aria-hidden="true" />
                Registering
              </>
            ) : (
              "Register patient"
            )}
          </Button>
        </form>
      </PanelBody>
    </>
  );
}
