"use client";

import { CheckCircle2, FileSpreadsheet, Loader2, UploadCloud } from "lucide-react";
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { PanelBody, PanelHeader } from "@/components/ui/panel";
import { cn } from "@/lib/cn";
import type { BulkUploadReport } from "@/lib/types";

const ACCEPTED = ".xlsx,.xlsm,.csv,.txt";

/**
 * Drag-and-drop bulk import.
 *
 * The file is posted to a route handler rather than the API directly, because
 * the session token lives in an httpOnly cookie the browser cannot read.
 *
 * The response is a *report*, not a success. Rows are validated independently,
 * so a thousand-row file with two bad rows still imports nine hundred and
 * ninety-eight patients, and the operator needs to see exactly which two failed
 * and why.
 */
export function BulkUpload({ hospitalId }: { hospitalId: string }) {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [pending, setPending] = useState(false);
  const [report, setReport] = useState<BulkUploadReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [fileName, setFileName] = useState<string | null>(null);

  async function upload(file: File) {
    setPending(true);
    setError(null);
    setReport(null);
    setFileName(file.name);

    const body = new FormData();
    body.append("file", file);
    body.append("hospital_id", hospitalId);

    try {
      const response = await fetch("/api/patients/bulk", { method: "POST", body });
      const payload = (await response.json()) as {
        error?: string;
        report?: BulkUploadReport;
      };

      if (!response.ok || !payload.report) {
        setError(payload.error ?? "The file could not be imported.");
      } else {
        setReport(payload.report);
        if (payload.report.accepted > 0) router.refresh();
      }
    } catch {
      setError("The upload could not be sent. Check your connection and try again.");
    } finally {
      setPending(false);
    }
  }

  function handleDrop(event: React.DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragging(false);
    const file = event.dataTransfer.files?.[0];
    if (file) void upload(file);
  }

  return (
    <>
      <PanelHeader
        title="Bulk import"
        description="Every cell is read as raw text, so an MRN of 0012 stays 0012 rather than becoming the number 12."
      />
      <PanelBody>
        <div
          onDragOver={(event) => {
            event.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={handleDrop}
          className={cn(
            "rounded-lg border border-dashed px-4 py-8 text-center transition-colors duration-150",
            dragging ? "border-primary bg-primary-muted" : "border-border bg-surface-muted",
          )}
        >
          <UploadCloud
            className={cn(
              "mx-auto size-6",
              dragging ? "text-primary" : "text-muted-foreground",
            )}
            strokeWidth={1.75}
            aria-hidden="true"
          />
          <p className="mt-2 text-sm font-medium text-foreground">
            Drop an .xlsx or .csv patient file here
          </p>
          <p className="mt-1 text-xs text-muted-foreground">
            Required columns: mrn, full_name, gender. Common export headers such as
            &ldquo;Medical Record Number&rdquo; and &ldquo;Patient Name&rdquo; are
            recognised.
          </p>

          <input
            ref={inputRef}
            type="file"
            accept={ACCEPTED}
            className="sr-only"
            aria-label="Choose a patient file to import"
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) void upload(file);
              event.target.value = "";
            }}
          />

          <Button
            type="button"
            variant="secondary"
            size="sm"
            className="mt-4"
            disabled={pending}
            onClick={() => inputRef.current?.click()}
          >
            {pending ? (
              <>
                <Loader2 className="animate-spin" strokeWidth={1.75} aria-hidden="true" />
                Importing
              </>
            ) : (
              <>
                <FileSpreadsheet strokeWidth={1.75} aria-hidden="true" />
                Choose a file
              </>
            )}
          </Button>
        </div>

        {error ? (
          <p
            role="alert"
            className="mt-4 rounded-md bg-critical-muted px-3 py-2 text-sm text-critical"
          >
            {error}
          </p>
        ) : null}

        {report ? <Report report={report} fileName={fileName} /> : null}
      </PanelBody>
    </>
  );
}

function Report({
  report,
  fileName,
}: {
  report: BulkUploadReport;
  fileName: string | null;
}) {
  const clean = report.rejected === 0;

  return (
    <div role="status" className="mt-4">
      <div
        className={cn(
          "flex items-start gap-2 rounded-md px-3 py-2 text-sm",
          clean ? "bg-stable-muted text-stable" : "bg-warning-muted text-warning",
        )}
      >
        <CheckCircle2 className="mt-0.5 size-4 shrink-0" strokeWidth={1.75} aria-hidden="true" />
        <p>
          {fileName ? `${fileName}: ` : ""}
          <span className="font-mono tabular-nums">{report.accepted}</span> of{" "}
          <span className="font-mono tabular-nums">{report.total_rows}</span> rows imported
          {clean ? "." : `, ${report.rejected} rejected.`}
        </p>
      </div>

      {report.errors.length > 0 ? (
        <div className="mt-3 overflow-hidden rounded-md border border-border">
          <table className="w-full text-sm">
            <thead className="bg-surface-muted text-muted-foreground">
              <tr>
                <th scope="col" className="px-3 py-2 text-left text-xs font-medium uppercase tracking-wide">
                  Row
                </th>
                <th scope="col" className="px-3 py-2 text-left text-xs font-medium uppercase tracking-wide">
                  Field
                </th>
                <th scope="col" className="px-3 py-2 text-left text-xs font-medium uppercase tracking-wide">
                  Reason
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {report.errors.map((rowError) => (
                <tr key={`${rowError.row_number}-${rowError.field ?? "row"}`}>
                  <td className="px-3 py-2 font-mono tabular-nums">{rowError.row_number}</td>
                  <td className="px-3 py-2 font-mono text-xs">{rowError.field ?? "row"}</td>
                  <td className="px-3 py-2 text-muted-foreground">{rowError.message}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  );
}
