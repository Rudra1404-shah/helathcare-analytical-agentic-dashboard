import type * as React from "react";

import { cn } from "@/lib/cn";
import { humanise } from "@/lib/format";
import type {
  AccreditationStatus,
  CaseStatus,
  InvestigationStatus,
  PaymentStatus,
  StaffStatus,
  TriageLevel,
} from "@/lib/types";

/**
 * Status badges. Colour is never the only signal: every badge carries a text
 * label, so a colourblind clinician reads exactly what everybody else reads.
 */

type Tone = "critical" | "warning" | "stable" | "info" | "neutral" | "primary";

const TONE_CLASS: Record<Tone, string> = {
  critical: "bg-critical-muted text-critical",
  warning: "bg-warning-muted text-warning",
  stable: "bg-stable-muted text-stable",
  info: "bg-info-muted text-info",
  neutral: "bg-neutral-muted text-muted-foreground",
  primary: "bg-primary-muted text-primary",
};

export function Badge({
  tone = "neutral",
  className,
  children,
  ...props
}: React.HTMLAttributes<HTMLSpanElement> & { tone?: Tone }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-xs font-medium",
        TONE_CLASS[tone],
        className,
      )}
      {...props}
    >
      {children}
    </span>
  );
}

// --------------------------------------------------------------------------
// Domain badges. Each maps a stored enum to a tone plus readable text.
// --------------------------------------------------------------------------

const CASE_TONE: Record<CaseStatus, Tone> = {
  ICU: "critical",
  ADMITTED: "info",
  OBSERVATION: "warning",
  DISCHARGED: "stable",
  DECEASED: "neutral",
};

export function CaseStatusBadge({ status }: { status: CaseStatus }) {
  return <Badge tone={CASE_TONE[status]}>{humanise(status)}</Badge>;
}

const TRIAGE_TONE: Record<TriageLevel, Tone> = {
  1: "critical",
  2: "warning",
  3: "info",
  4: "neutral",
};

const TRIAGE_LABEL: Record<TriageLevel, string> = {
  1: "Immediate",
  2: "Urgent",
  3: "Standard",
  4: "Non-urgent",
};

export function TriageBadge({ level }: { level: TriageLevel | null }) {
  if (level === null) {
    return <Badge tone="neutral">Untriaged</Badge>;
  }
  return (
    <Badge tone={TRIAGE_TONE[level]}>
      <span className="font-mono tabular-nums">{level}</span>
      {TRIAGE_LABEL[level]}
    </Badge>
  );
}

const ACCREDITATION_TONE: Record<AccreditationStatus, Tone> = {
  NABH: "stable",
  STATE_LICENSED: "info",
  PENDING: "warning",
  BLACKLISTED: "critical",
};

export function AccreditationBadge({ status }: { status: AccreditationStatus }) {
  return <Badge tone={ACCREDITATION_TONE[status]}>{humanise(status)}</Badge>;
}

const PAYMENT_TONE: Record<PaymentStatus, Tone> = {
  PAID: "stable",
  PARTIALLY_PAID: "warning",
  PENDING: "info",
  CANCELLED: "neutral",
  REFUNDED: "neutral",
};

export function PaymentBadge({ status }: { status: PaymentStatus }) {
  return <Badge tone={PAYMENT_TONE[status]}>{humanise(status)}</Badge>;
}

const INVESTIGATION_TONE: Record<InvestigationStatus, Tone> = {
  SUBMITTED: "warning",
  UNDER_REVIEW: "info",
  INQUIRY_ASSIGNED: "info",
  ACTION_TAKEN: "stable",
  DISMISSED: "neutral",
};

export function InvestigationBadge({ status }: { status: InvestigationStatus }) {
  return <Badge tone={INVESTIGATION_TONE[status]}>{humanise(status)}</Badge>;
}

const STAFF_TONE: Record<StaffStatus, Tone> = {
  ACTIVE: "stable",
  ON_LEAVE: "warning",
  INACTIVE: "neutral",
  SUSPENDED: "critical",
  TERMINATED: "neutral",
};

export function StaffStatusBadge({ status }: { status: StaffStatus }) {
  return <Badge tone={STAFF_TONE[status]}>{humanise(status)}</Badge>;
}
