"use client";

import { CheckCircle2, Loader2 } from "lucide-react";
import { useState, useTransition } from "react";

import { updateInvestigation } from "@/app/(gov)/gov/actions";
import { Button } from "@/components/ui/button";
import { Field, Select, Textarea } from "@/components/ui/field";
import { humanise } from "@/lib/format";
import type { ActionTaken, Complaint, InvestigationStatus } from "@/lib/types";

const OPEN_STATUSES: InvestigationStatus[] = [
  "SUBMITTED",
  "UNDER_REVIEW",
  "INQUIRY_ASSIGNED",
];
const CLOSING_STATUSES: InvestigationStatus[] = ["ACTION_TAKEN", "DISMISSED"];
const ACTIONS: ActionTaken[] = ["WARNING", "FINE", "LICENSE_SUSPENSION", "DISMISSED"];

export function InvestigationForm({ complaint }: { complaint: Complaint }) {
  const closed = complaint.closed_at !== null;
  const [status, setStatus] = useState<InvestigationStatus>(
    complaint.investigation_status,
  );
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [pending, startTransition] = useTransition();

  if (closed) {
    return (
      <p className="flex items-start gap-2 text-sm text-muted-foreground">
        <CheckCircle2
          className="mt-0.5 size-4 shrink-0 text-stable"
          strokeWidth={1.75}
          aria-hidden="true"
        />
        Closed as {humanise(complaint.investigation_status).toLowerCase()}. A resolution
        cannot be rewritten once recorded.
      </p>
    );
  }

  const closing = CLOSING_STATUSES.includes(status);

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setSaved(false);
    const formData = new FormData(event.currentTarget);

    startTransition(async () => {
      const result = await updateInvestigation(complaint._id, formData);
      if (result.ok) {
        setSaved(true);
      } else {
        setError(result.error ?? "The investigation could not be updated.");
      }
    });
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4">
      <Field label="Investigation status" htmlFor="investigation_status" required>
        <Select
          id="investigation_status"
          name="investigation_status"
          value={status}
          onChange={(event) => setStatus(event.target.value as InvestigationStatus)}
          disabled={pending}
        >
          <optgroup label="Open">
            {OPEN_STATUSES.map((option) => (
              <option key={option} value={option}>
                {humanise(option)}
              </option>
            ))}
          </optgroup>
          <optgroup label="Closes the investigation">
            {CLOSING_STATUSES.map((option) => (
              <option key={option} value={option}>
                {humanise(option)}
              </option>
            ))}
          </optgroup>
        </Select>
      </Field>

      <Field
        label="Hospital explanation"
        htmlFor="hospital_explanation"
        hint="What the hospital said when asked."
      >
        <Textarea
          id="hospital_explanation"
          name="hospital_explanation"
          defaultValue={complaint.hospital_explanation ?? ""}
          disabled={pending}
          className="min-h-20"
        />
      </Field>

      {closing ? (
        <>
          <Field label="Action taken" htmlFor="action_taken" required>
            <Select id="action_taken" name="action_taken" disabled={pending} required>
              {ACTIONS.map((action) => (
                <option key={action} value={action}>
                  {humanise(action)}
                </option>
              ))}
            </Select>
          </Field>

          <Field
            label="Closure remarks"
            htmlFor="closure_remarks"
            hint="Why this decision was reached. Feeds the impact-tracking module."
            required
          >
            <Textarea
              id="closure_remarks"
              name="closure_remarks"
              required
              disabled={pending}
              className="min-h-20"
            />
          </Field>
        </>
      ) : null}

      {error ? (
        <p role="alert" className="rounded-md bg-critical-muted px-3 py-2 text-sm text-critical">
          {error}
        </p>
      ) : null}

      {saved ? (
        <p role="status" className="rounded-md bg-stable-muted px-3 py-2 text-sm text-stable">
          Investigation updated.
        </p>
      ) : null}

      <Button type="submit" disabled={pending}>
        {pending ? (
          <>
            <Loader2 className="animate-spin" strokeWidth={1.75} aria-hidden="true" />
            Saving
          </>
        ) : closing ? (
          "Close investigation"
        ) : (
          "Update investigation"
        )}
      </Button>
    </form>
  );
}
