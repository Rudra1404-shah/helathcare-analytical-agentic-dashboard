"use client";

import {
  CheckCircle2,
  Film,
  ImageIcon,
  Loader2,
  ShieldAlert,
  Trash2,
  UploadCloud,
} from "lucide-react";
import { useRef, useState, useTransition } from "react";

import { submitComplaint } from "@/app/(citizen)/citizen/actions";
import { Button } from "@/components/ui/button";
import { Field, Select, Textarea } from "@/components/ui/field";
import { PanelBody, PanelHeader } from "@/components/ui/panel";
import { cn } from "@/lib/cn";
import { humanise } from "@/lib/format";
import type { ComplaintCategory, EvidenceType, Hospital, UploadedFile } from "@/lib/types";

const CATEGORIES: ComplaintCategory[] = [
  "OVERCHARGING",
  "BED_REFUSAL",
  "NEGLIGENCE",
  "HYGIENE",
  "SHORTAGE",
  "FALSE_BILLING",
];

const MIN_DESCRIPTION = 50;

interface Attachment extends UploadedFile {
  evidence_type: EvidenceType;
}

/**
 * The Public Complaint Form.
 *
 * Evidence is mandatory, and the submit button stays disabled until at least
 * one photo or video is attached. The API enforces the same rule at three
 * layers; disabling the control here means a citizen learns it before typing
 * six hundred words, not after.
 */
export function ComplaintForm({ hospitals }: { hospitals: Hospital[] }) {
  const inputRef = useRef<HTMLInputElement>(null);
  const formRef = useRef<HTMLFormElement>(null);

  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [description, setDescription] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [reference, setReference] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  const hasEvidence = attachments.length > 0;
  const longEnough = description.trim().length >= MIN_DESCRIPTION;
  const canSubmit = hasEvidence && longEnough && !pending && !uploading;

  async function uploadFile(file: File) {
    const isVideo = file.type.startsWith("video/");
    const evidenceType: EvidenceType = isVideo ? "VIDEO" : "PHOTO";

    setUploading(true);
    setUploadError(null);

    const body = new FormData();
    body.append("file", file);
    body.append("evidence_type", evidenceType);

    try {
      const response = await fetch("/api/uploads/evidence", { method: "POST", body });
      const payload = (await response.json()) as { error?: string; file?: UploadedFile };

      if (!response.ok || !payload.file) {
        setUploadError(payload.error ?? "The attachment could not be uploaded.");
      } else {
        setAttachments((current) => [...current, { ...payload.file!, evidence_type: evidenceType }]);
      }
    } catch {
      setUploadError("The upload could not be sent. Check your connection.");
    } finally {
      setUploading(false);
    }
  }

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setReference(null);

    const formData = new FormData(event.currentTarget);
    formData.set("evidence", JSON.stringify(attachments));

    startTransition(async () => {
      const result = await submitComplaint(formData);
      if (result.ok) {
        setReference(result.complaintNumber ?? null);
        setAttachments([]);
        setDescription("");
        formRef.current?.reset();
      } else {
        setError(result.error ?? "The complaint could not be submitted.");
      }
    });
  }

  if (reference) {
    return (
      <>
        <PanelHeader title="Complaint filed" />
        <PanelBody>
          <div className="flex flex-col items-center py-8 text-center">
            <CheckCircle2 className="size-7 text-stable" strokeWidth={1.75} aria-hidden="true" />
            <h2 className="mt-3 text-sm font-semibold text-foreground">
              Your complaint has been filed
            </h2>
            <p className="mt-1 max-w-[46ch] text-sm text-muted-foreground">
              Quote this reference when you follow it up. The Health Ministry will review the
              evidence you submitted and record the outcome against it.
            </p>
            <p className="mt-4 rounded-md bg-surface-muted px-4 py-2 font-mono text-base font-semibold text-foreground">
              {reference}
            </p>
            <Button
              variant="secondary"
              className="mt-5"
              onClick={() => setReference(null)}
            >
              File another complaint
            </Button>
          </div>
        </PanelBody>
      </>
    );
  }

  return (
    <>
      <PanelHeader
        title="File a complaint"
        description="At least one photograph or video is required. A grievance the ministry cannot substantiate cannot be enforced."
      />
      <PanelBody>
        <form ref={formRef} onSubmit={handleSubmit} className="flex flex-col gap-5">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Hospital" htmlFor="hospital_id" required>
              <Select id="hospital_id" name="hospital_id" required disabled={pending}>
                <option value="">Choose a hospital</option>
                {hospitals.map((hospital) => (
                  <option key={hospital._id} value={hospital._id}>
                    {hospital.name}, {hospital.city}
                  </option>
                ))}
              </Select>
            </Field>

            <Field label="What went wrong" htmlFor="category" required>
              <Select id="category" name="category" required disabled={pending}>
                {CATEGORIES.map((category) => (
                  <option key={category} value={category}>
                    {humanise(category)}
                  </option>
                ))}
              </Select>
            </Field>
          </div>

          <Field
            label="When did it happen"
            htmlFor="incident_at"
            hint="An incident cannot be reported before it happens."
            required
          >
            <input
              id="incident_at"
              name="incident_at"
              type="datetime-local"
              required
              disabled={pending}
              max={new Date().toISOString().slice(0, 16)}
              className="h-9 w-full rounded-md border border-border bg-surface px-3 text-sm text-foreground sm:w-auto"
            />
          </Field>

          <Field
            label="What happened"
            htmlFor="description"
            hint={`At least ${MIN_DESCRIPTION} characters, so an official can investigate it.`}
            error={
              description.length > 0 && !longEnough
                ? `${MIN_DESCRIPTION - description.trim().length} more characters needed.`
                : null
            }
            required
          >
            <Textarea
              id="description"
              name="description"
              required
              disabled={pending}
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              className="min-h-32"
              placeholder="Describe what happened, when, and who was involved."
            />
          </Field>

          <fieldset>
            <legend className="text-sm font-medium text-foreground">
              Evidence
              <span className="ml-1 text-xs font-normal text-muted-foreground">
                (required)
              </span>
            </legend>
            <p className="mt-1 text-xs text-muted-foreground">
              Photographs or video showing what you are reporting. JPEG, PNG, WebP, MP4,
              MOV, or WebM.
            </p>

            <div
              onDragOver={(event) => {
                event.preventDefault();
                setDragging(true);
              }}
              onDragLeave={() => setDragging(false)}
              onDrop={(event) => {
                event.preventDefault();
                setDragging(false);
                const file = event.dataTransfer.files?.[0];
                if (file) void uploadFile(file);
              }}
              className={cn(
                "mt-3 rounded-lg border border-dashed px-4 py-7 text-center transition-colors duration-150",
                dragging
                  ? "border-primary bg-primary-muted"
                  : hasEvidence
                    ? "border-border bg-surface-muted"
                    : "border-critical bg-critical-muted",
              )}
            >
              {hasEvidence ? (
                <UploadCloud
                  className="mx-auto size-6 text-muted-foreground"
                  strokeWidth={1.75}
                  aria-hidden="true"
                />
              ) : (
                <ShieldAlert
                  className="mx-auto size-6 text-critical"
                  strokeWidth={1.75}
                  aria-hidden="true"
                />
              )}
              <p
                className={cn(
                  "mt-2 text-sm font-medium",
                  hasEvidence ? "text-foreground" : "text-critical",
                )}
              >
                {hasEvidence
                  ? "Add another photo or video"
                  : "A photo or video is required to submit"}
              </p>

              <input
                ref={inputRef}
                type="file"
                accept="image/jpeg,image/png,image/webp,image/heic,video/mp4,video/quicktime,video/webm"
                className="sr-only"
                aria-label="Choose a photo or video as evidence"
                onChange={(event) => {
                  const file = event.target.files?.[0];
                  if (file) void uploadFile(file);
                  event.target.value = "";
                }}
              />

              <Button
                type="button"
                variant="secondary"
                size="sm"
                className="mt-3"
                disabled={uploading || pending}
                onClick={() => inputRef.current?.click()}
              >
                {uploading ? (
                  <>
                    <Loader2 className="animate-spin" strokeWidth={1.75} aria-hidden="true" />
                    Uploading
                  </>
                ) : (
                  "Choose a file"
                )}
              </Button>
            </div>

            {uploadError ? (
              <p
                role="alert"
                className="mt-2 rounded-md bg-critical-muted px-3 py-2 text-sm text-critical"
              >
                {uploadError}
              </p>
            ) : null}

            {attachments.length > 0 ? (
              <ul className="mt-3 flex flex-col gap-2">
                {attachments.map((attachment) => {
                  const Icon = attachment.evidence_type === "VIDEO" ? Film : ImageIcon;
                  return (
                    <li
                      key={attachment.url}
                      className="flex items-center gap-3 rounded-md border border-border px-3 py-2"
                    >
                      <Icon
                        className="size-4 shrink-0 text-muted-foreground"
                        strokeWidth={1.75}
                        aria-hidden="true"
                      />
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm text-foreground">
                          {attachment.file_name}
                        </p>
                        <p className="text-xs text-muted-foreground">
                          {humanise(attachment.evidence_type)} ·{" "}
                          <span className="font-mono tabular-nums">
                            {(attachment.size_bytes / 1024).toFixed(0)} KB
                          </span>
                        </p>
                      </div>
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        aria-label={`Remove ${attachment.file_name}`}
                        disabled={pending}
                        onClick={() =>
                          setAttachments((current) =>
                            current.filter((item) => item.url !== attachment.url),
                          )
                        }
                      >
                        <Trash2 strokeWidth={1.75} aria-hidden="true" />
                      </Button>
                    </li>
                  );
                })}
              </ul>
            ) : null}
          </fieldset>

          {error ? (
            <p
              role="alert"
              className="rounded-md bg-critical-muted px-3 py-2 text-sm text-critical"
            >
              {error}
            </p>
          ) : null}

          <div>
            <Button type="submit" disabled={!canSubmit} className="w-full sm:w-auto">
              {pending ? (
                <>
                  <Loader2 className="animate-spin" strokeWidth={1.75} aria-hidden="true" />
                  Submitting
                </>
              ) : (
                "Submit complaint"
              )}
            </Button>
            {!hasEvidence ? (
              <p className="mt-2 text-xs text-muted-foreground">
                Attach a photo or video to enable this.
              </p>
            ) : null}
          </div>
        </form>
      </PanelBody>
    </>
  );
}
