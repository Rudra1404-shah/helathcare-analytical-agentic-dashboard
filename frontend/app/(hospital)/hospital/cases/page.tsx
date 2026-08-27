import { Activity, HeartPulse } from "lucide-react";
import type { Metadata } from "next";
import { Suspense } from "react";

import { CaseStatusBadge, TriageBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { FilterSelect } from "@/components/ui/field";
import { PageHeader, Panel, PanelHeader } from "@/components/ui/panel";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/ui/states";
import { Table, TBody, TD, TDMeta, TDPrimary, TH, THead, TR, TableWrap } from "@/components/ui/table";
import { apiTry } from "@/lib/api";
import { cn } from "@/lib/cn";
import { dateTime, humanise, stayDuration } from "@/lib/format";
import { withHospital } from "@/lib/hospital-page";
import type { CaseStatus, Paginated, Patient, PatientCase, VitalSigns } from "@/lib/types";

export const metadata: Metadata = { title: "Cases and triage" };

const STATUSES: CaseStatus[] = [
  "ADMITTED",
  "ICU",
  "OBSERVATION",
  "DISCHARGED",
  "DECEASED",
];

interface Filters {
  view?: string;
  status?: CaseStatus;
}

export default async function CasesPage({
  searchParams,
}: {
  searchParams: Promise<Filters>;
}) {
  const filters = await searchParams;
  const board = filters.view !== "register";

  return withHospital("Cases and triage", (hospital) => (
    <>
      <PageHeader
        title="Cases and triage"
        description="Open encounters grouped by clinical urgency. Cases with no triage assigned are surfaced rather than hidden, because an unclassified patient is exactly the one a charge nurse needs to see."
      />

      <Panel className="p-3">
        <form className="flex flex-wrap items-end gap-3">
          <FilterSelect label="Arrangement" name="view" defaultValue={filters.view ?? ""}>
            <option value="">Triage board</option>
            <option value="register">Full register</option>
          </FilterSelect>

          {!board ? null : null}

          <FilterSelect label="Status" name="status" defaultValue={filters.status ?? ""}>
            <option value="">Any status</option>
            {STATUSES.map((status) => (
              <option key={status} value={status}>
                {humanise(status)}
              </option>
            ))}
          </FilterSelect>

          <Button type="submit" size="sm">
            Apply
          </Button>
        </form>
      </Panel>

      <div className="mt-4">
        <Suspense
          key={JSON.stringify(filters)}
          fallback={
            <Panel>
              <PanelHeader title="Loading cases" />
              <TableSkeleton rows={8} columns={5} />
            </Panel>
          }
        >
          {board ? (
            <TriageBoard hospitalId={hospital._id} />
          ) : (
            <Panel>
              <CaseRegister hospitalId={hospital._id} status={filters.status} />
            </Panel>
          )}
        </Suspense>
      </div>
    </>
  ));
}

const COLUMN_ORDER = ["IMMEDIATE", "URGENT", "STANDARD", "NON_URGENT", "UNTRIAGED"];

const COLUMN_LABEL: Record<string, string> = {
  IMMEDIATE: "Immediate",
  URGENT: "Urgent",
  STANDARD: "Standard",
  NON_URGENT: "Non-urgent",
  UNTRIAGED: "Untriaged",
};

const COLUMN_ACCENT: Record<string, string> = {
  IMMEDIATE: "border-t-critical",
  URGENT: "border-t-warning",
  STANDARD: "border-t-info",
  NON_URGENT: "border-t-neutral",
  UNTRIAGED: "border-t-critical",
};

async function TriageBoard({ hospitalId }: { hospitalId: string }) {
  const result = await apiTry<Record<string, PatientCase[]>>(
    `/hospitals/${hospitalId}/cases/triage-board`,
  );

  if (!result.ok) {
    return (
      <Panel>
        <ErrorState message={result.error} />
      </Panel>
    );
  }

  const board = result.data;
  const columns = COLUMN_ORDER.filter((key) => (board[key]?.length ?? 0) > 0);

  if (columns.length === 0) {
    return (
      <Panel>
        <EmptyState
          icon={HeartPulse}
          title="No open cases"
          description="Every case at this hospital has been closed. New admissions appear on the board as soon as they are opened."
        />
      </Panel>
    );
  }

  return (
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
      {columns.map((key) => (
        <section key={key} className={cn("rounded-lg border border-t-2 border-border bg-surface", COLUMN_ACCENT[key])}>
          <header className="flex items-baseline justify-between gap-2 border-b border-border px-4 py-3">
            <h2 className="text-sm font-semibold text-foreground">{COLUMN_LABEL[key]}</h2>
            <span className="font-mono text-xs tabular-nums text-muted-foreground">
              {board[key].length}
            </span>
          </header>
          <ul className="divide-y divide-border">
            {board[key].map((item) => (
              <li key={item._id} className="px-4 py-3">
                <div className="flex items-start justify-between gap-2">
                  <p className="font-mono text-xs font-medium text-foreground">
                    {item.case_number}
                  </p>
                  <CaseStatusBadge status={item.status} />
                </div>
                <p className="mt-1 text-sm text-foreground">
                  {item.chief_symptoms.join(", ")}
                </p>
                <p className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
                  <span>Bed {item.bed_allocated ?? "unassigned"}</span>
                  <span className="font-mono tabular-nums">
                    {stayDuration(item.admitted_at, item.discharged_at)}
                  </span>
                </p>
                <LatestVitals vitals={item.vitals} />
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}

/**
 * The most recent observation set. Vitals accumulate as a list rather than a
 * snapshot because deterioration is only visible as a trend, so the count of
 * readings is shown alongside the latest values.
 */
function LatestVitals({ vitals }: { vitals: VitalSigns[] }) {
  if (vitals.length === 0) {
    return (
      <p className="mt-2 text-xs text-muted-foreground">No observations recorded yet.</p>
    );
  }

  const latest = vitals.reduce((newest, reading) =>
    new Date(reading.recorded_at) > new Date(newest.recorded_at) ? reading : newest,
  );

  const lowOxygen = latest.spo2_percent < 92;
  const feverish = latest.temperature_celsius >= 38;

  return (
    <dl className="mt-2 flex flex-wrap gap-x-3 gap-y-1 font-mono text-xs tabular-nums">
      <div className="flex gap-1">
        <dt className="text-muted-foreground">BP</dt>
        <dd className="text-foreground">
          {latest.systolic_bp}/{latest.diastolic_bp}
        </dd>
      </div>
      <div className="flex gap-1">
        <dt className="text-muted-foreground">HR</dt>
        <dd className="text-foreground">{latest.pulse_bpm}</dd>
      </div>
      <div className="flex gap-1">
        <dt className="text-muted-foreground">SpO2</dt>
        <dd className={lowOxygen ? "font-semibold text-critical" : "text-foreground"}>
          {latest.spo2_percent}%
        </dd>
      </div>
      <div className="flex gap-1">
        <dt className="text-muted-foreground">Temp</dt>
        <dd className={feverish ? "font-semibold text-warning" : "text-foreground"}>
          {latest.temperature_celsius}
        </dd>
      </div>
      <div className="flex gap-1">
        <dt className="text-muted-foreground">Readings</dt>
        <dd className="text-foreground">{vitals.length}</dd>
      </div>
    </dl>
  );
}

async function CaseRegister({
  hospitalId,
  status,
}: {
  hospitalId: string;
  status?: CaseStatus;
}) {
  const [cases, patients] = await Promise.all([
    apiTry<Paginated<PatientCase>>(`/hospitals/${hospitalId}/cases`, {
      query: { status, limit: 100 },
    }),
    apiTry<Paginated<Patient>>(`/hospitals/${hospitalId}/patients`, {
      query: { limit: 200 },
    }),
  ]);

  if (!cases.ok) {
    return (
      <>
        <PanelHeader title="Case register" />
        <ErrorState message={cases.error} />
      </>
    );
  }

  const patientName = new Map(
    patients.ok ? patients.data.items.map((item) => [item._id, item.full_name]) : [],
  );

  const { items, meta } = cases.data;

  if (items.length === 0) {
    return (
      <>
        <PanelHeader title="Case register" />
        <EmptyState
          icon={Activity}
          title="No cases match this filter"
          description="Admit a patient to open a case. Admission reserves a bed from the matching inventory pool, so the register and the capacity view can never disagree."
        />
      </>
    );
  }

  return (
    <>
      <PanelHeader title="Case register" description={`${meta.total} recorded`} />
      <TableWrap>
        <Table>
          <THead>
            <tr>
              <TH>Case</TH>
              <TH>Patient</TH>
              <TH>Triage</TH>
              <TH>Status</TH>
              <TH>Admitted</TH>
              <TH numeric>Stay</TH>
            </tr>
          </THead>
          <TBody>
            {items.map((item) => (
              <TR key={item._id}>
                <TDPrimary>
                  <span className="font-mono text-xs">{item.case_number}</span>
                  <TDMeta>{item.chief_symptoms.join(", ")}</TDMeta>
                </TDPrimary>
                <TD>
                  {patientName.get(item.patient_id) ?? "Record not visible"}
                  <TDMeta>Bed {item.bed_allocated ?? "unassigned"}</TDMeta>
                </TD>
                <TD>
                  <TriageBadge level={item.triage_level} />
                </TD>
                <TD>
                  <CaseStatusBadge status={item.status} />
                </TD>
                <TD>{dateTime(item.admitted_at)}</TD>
                <TD numeric>{stayDuration(item.admitted_at, item.discharged_at)}</TD>
              </TR>
            ))}
          </TBody>
        </Table>
      </TableWrap>
    </>
  );
}
