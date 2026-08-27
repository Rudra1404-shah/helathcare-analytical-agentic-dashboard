"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { FileWarning, Maximize2, X } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { dateTime } from "@/lib/format";
import type { EvidenceAttachment } from "@/lib/types";

/**
 * The evidence viewer for the ministry investigation form.
 *
 * Renders by the citizen's declared type, which is why the API refuses an
 * attachment whose MIME type contradicts it: a video filed as a photo would
 * show a broken frame here instead of the evidence.
 */
export function EvidenceGallery({ evidence }: { evidence: EvidenceAttachment[] }) {
  if (evidence.length === 0) {
    // The API cannot produce this: evidence is mandatory at three layers.
    // Rendering it anyway means a stored complaint would never look empty by
    // accident.
    return (
      <p className="flex items-center gap-2 text-sm text-critical">
        <FileWarning className="size-4" strokeWidth={1.75} aria-hidden="true" />
        This complaint carries no evidence, which should not be possible.
      </p>
    );
  }

  return (
    <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3">
      {evidence.map((attachment) => (
        <li key={attachment.url}>
          <EvidenceTile attachment={attachment} />
        </li>
      ))}
    </ul>
  );
}

function EvidenceTile({ attachment }: { attachment: EvidenceAttachment }) {
  const [failed, setFailed] = useState(false);
  const isPhoto = attachment.evidence_type === "PHOTO";
  const label = `${isPhoto ? "Photograph" : "Video"} submitted ${dateTime(attachment.uploaded_at)}`;

  return (
    <Dialog.Root>
      <Dialog.Trigger asChild>
        <button
          type="button"
          className="group relative block w-full overflow-hidden rounded-md border border-border bg-surface-muted transition-colors duration-150 hover:border-primary"
          aria-label={`Open ${label}`}
        >
          <div className="aspect-[4/3] w-full">
            {failed ? (
              <div className="flex h-full flex-col items-center justify-center gap-1.5 px-2 text-center">
                <FileWarning
                  className="size-5 text-muted-foreground"
                  strokeWidth={1.75}
                  aria-hidden="true"
                />
                <span className="text-xs text-muted-foreground">
                  Media could not be loaded
                </span>
              </div>
            ) : isPhoto ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={attachment.url}
                alt={label}
                className="h-full w-full object-cover"
                onError={() => setFailed(true)}
              />
            ) : (
              <video
                src={attachment.url}
                className="h-full w-full object-cover"
                muted
                playsInline
                preload="metadata"
                onError={() => setFailed(true)}
              />
            )}
          </div>
          <span className="absolute right-1.5 top-1.5 rounded-md bg-slate-950/70 p-1 text-white opacity-0 transition-opacity duration-150 group-hover:opacity-100">
            <Maximize2 className="size-3.5" strokeWidth={1.75} aria-hidden="true" />
          </span>
        </button>
      </Dialog.Trigger>

      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-slate-950/70" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-[min(56rem,calc(100vw-2rem))] -translate-x-1/2 -translate-y-1/2 rounded-lg border border-border bg-surface p-4 shadow-lg">
          <div className="mb-3 flex items-start justify-between gap-3">
            <div className="min-w-0">
              <Dialog.Title className="text-sm font-semibold text-foreground">
                {isPhoto ? "Photographic evidence" : "Video evidence"}
              </Dialog.Title>
              <Dialog.Description className="mt-0.5 truncate text-xs text-muted-foreground">
                {attachment.file_name ?? "Attachment"} · {attachment.content_type} ·{" "}
                {(attachment.size_bytes / 1024).toFixed(0)} KB · uploaded{" "}
                {dateTime(attachment.uploaded_at)}
              </Dialog.Description>
            </div>
            <Dialog.Close asChild>
              <Button variant="ghost" size="icon" aria-label="Close evidence">
                <X strokeWidth={1.75} aria-hidden="true" />
              </Button>
            </Dialog.Close>
          </div>

          <div className="overflow-hidden rounded-md bg-surface-muted">
            {isPhoto ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={attachment.url}
                alt={label}
                className="max-h-[70dvh] w-full object-contain"
              />
            ) : (
              <video
                src={attachment.url}
                controls
                className="max-h-[70dvh] w-full"
                aria-label={label}
              />
            )}
          </div>

          {attachment.checksum_sha256 ? (
            <p className="mt-3 truncate font-mono text-xs text-muted-foreground">
              SHA-256 {attachment.checksum_sha256}
            </p>
          ) : null}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
