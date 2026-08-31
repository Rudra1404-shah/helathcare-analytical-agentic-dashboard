"use client";

import { Plus } from "lucide-react";
import { useState } from "react";

import { createCaseType } from "@/app/(hospital)/hospital/actions";
import { Button } from "@/components/ui/button";
import { FormDialog } from "@/components/ui/dialog";
import { Field, Input, Select, Textarea } from "@/components/ui/field";
import { useToast } from "@/components/ui/toast";
import { humanise } from "@/lib/format";
import type { DiseaseCategory } from "@/lib/types";

/**
 * Define a clinical protocol.
 *
 * The triage level set here becomes the default for every admission classified
 * against this type, which is why it is a required choice rather than a
 * sensible-looking default: getting it wrong silently mis-sorts a whole column
 * of the triage board.
 */

const CATEGORIES: DiseaseCategory[] = [
  "INFECTIOUS",
  "CHRONIC",
  "TRAUMA",
  "SURGICAL",
  "PEDIATRIC",
  "MATERNAL",
];

const TRIAGE = [
  { value: "1", label: "1 - Immediate", note: "Resuscitation. Seen without delay." },
  { value: "2", label: "2 - Urgent", note: "Seen within minutes." },
  { value: "3", label: "3 - Standard", note: "Seen in turn." },
  { value: "4", label: "4 - Non-urgent", note: "Can wait or be referred onward." },
];

export function CreateCaseTypeDialog() {
  const { confirm } = useToast();
  const [triage, setTriage] = useState("3");
  const [notifiable, setNotifiable] = useState(false);
  const chosen = TRIAGE.find((option) => option.value === triage);

  return (
    <FormDialog
      trigger={
        <Button size="sm">
          <Plus strokeWidth={1.75} aria-hidden="true" />
          Define case type
        </Button>
      }
      title="Define a case type"
      description="ICD-10 coded, with the triage level every admission of this kind inherits."
      submitLabel="Define case type"
      pendingLabel="Defining"
      action={createCaseType}
      onSuccess={() => confirm("Case type defined.")}
    >
      {({ pending }) => (
        <>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Name" htmlFor="name" required>
              <Input
                id="name"
                name="name"
                required
                disabled={pending}
                placeholder="Acute Gastroenteritis"
              />
            </Field>

            <Field
              label="ICD-10 code"
              htmlFor="icd10_code"
              hint="For example A09 or J18.9."
              required
            >
              <Input
                id="icd10_code"
                name="icd10_code"
                required
                className="font-mono uppercase"
                disabled={pending}
                placeholder="A09"
              />
            </Field>

            <Field label="Disease category" htmlFor="disease_category" required>
              <Select
                id="disease_category"
                name="disease_category"
                defaultValue="INFECTIOUS"
                disabled={pending}
              >
                {CATEGORIES.map((category) => (
                  <option key={category} value={category}>
                    {humanise(category)}
                  </option>
                ))}
              </Select>
            </Field>

            <Field label="Default triage" htmlFor="triage_level" required>
              <Select
                id="triage_level"
                name="triage_level"
                value={triage}
                onChange={(event) => setTriage(event.target.value)}
                disabled={pending}
              >
                {TRIAGE.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </Select>
            </Field>
          </div>

          {chosen ? <p className="text-sm text-muted-foreground">{chosen.note}</p> : null}

          <Field
            label="Clinical guidance"
            htmlFor="description"
            hint="Optional. Shown to the admitting clinician."
          >
            <Textarea
              id="description"
              name="description"
              maxLength={1000}
              disabled={pending}
              placeholder="Rehydrate orally where tolerated. Escalate to IV fluids if unable to keep fluids down for six hours."
            />
          </Field>

          <label htmlFor="is_notifiable" className="flex cursor-pointer items-start gap-2.5">
            <input
              id="is_notifiable"
              name="is_notifiable"
              type="checkbox"
              checked={notifiable}
              onChange={(event) => setNotifiable(event.target.checked)}
              disabled={pending}
              className="mt-0.5 size-4 shrink-0 rounded-[3px] border border-border accent-[var(--primary)]"
            />
            <span className="min-w-0">
              <span className="block text-sm text-foreground">Notifiable condition</span>
              <span className="block text-xs text-muted-foreground">
                Reported to the ministry and watched for anomalous clustering.
              </span>
            </span>
          </label>

          {notifiable ? (
            <p className="rounded-md bg-warning-muted px-3 py-2 text-sm text-warning">
              Every admission of this type is reported onward automatically. Mark it
              notifiable only where the national list requires it.
            </p>
          ) : null}
        </>
      )}
    </FormDialog>
  );
}
