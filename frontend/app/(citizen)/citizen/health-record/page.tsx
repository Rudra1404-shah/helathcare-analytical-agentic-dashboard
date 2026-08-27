import { Building2, FileHeart, Pill, Stethoscope } from "lucide-react";
import type { Metadata } from "next";
import { Suspense } from "react";

import { Badge, CaseStatusBadge, PaymentBadge } from "@/components/ui/badge";
import { PageHeader, Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import { CardsSkeleton, EmptyState, ErrorState, Skeleton } from "@/components/ui/states";
import { apiTry } from "@/lib/api";
import { dateTime, humanise, money, stayDuration } from "@/lib/format";
import type { HealthRecord, PhrCaseEntry, VitalSigns } from "@/lib/types";

export const metadata: Metadata = { title: "Health record" };

export default function HealthRecordPage() {
  return (
    <>
      <PageHeader
        title="Your health record"
        description="Every hospital that has treated you, assembled into one timeline. Records from a public hospital in one state and a private one in another resolve to the same person, because they are matched on your National ID rather than on a hospital's own file number."
      />
      <Suspense fallback={<RecordSkeleton />}>
        <Record />
      </Suspense>
    </>
  );
}

function RecordSkeleton() {
  return (
    <div className="flex flex-col gap-4">
      <CardsSkeleton count={3} />
      <Panel>
        <PanelHeader title="Your visits" description="Loading" />
        <PanelBody className="flex flex-col gap-3">
          <Skeleton className="h-24" />
          <Skeleton className="h-24" />
        </PanelBody>
      </Panel>
    </div>
  );
}

async function Record() {
  const result = await apiTry<HealthRecord>("/citizen/health-record");

  if (!result.ok) {
    return (
      <Panel>
        <ErrorState message={result.error} />
      </Panel>
    );
  }

  const record = result.data;
  const hospitals = new Set(record.cases.map((entry) => entry.hospital.hospital_id));

  return (
    <div className="flex flex-col gap-4">
      <Panel>
        <PanelHeader
          title={record.full_name}
          description={`Assembled ${dateTime(record.generated_at)}`}
        />
        <PanelBody>
          <dl className="grid gap-x-6 gap-y-4 sm:grid-cols-2 lg:grid-cols-4">
            <Summary label="Blood group" value={record.blood_group} />
            <Summary
              label="Age"
              value={record.age_years === null ? "Not recorded" : `${record.age_years} years`}
            />
            <Summary label="Hospitals visited" value={String(hospitals.size)} />
            <Summary label="Recorded visits" value={String(record.cases.length)} />
          </dl>

          {record.allergies.length > 0 || record.pre_existing_conditions.length > 0 ? (
            <div className="mt-5 grid gap-4 border-t border-border pt-4 sm:grid-cols-2">
              <div>
                <h3 className="text-sm font-medium text-foreground">Allergies</h3>
                <div className="mt-1.5 flex flex-wrap gap-1.5">
                  {record.allergies.length > 0 ? (
                    record.allergies.map((allergy) => (
                      <Badge key={allergy} tone="critical">
                        {allergy}
                      </Badge>
                    ))
                  ) : (
                    <span className="text-sm text-muted-foreground">None recorded</span>
                  )}
                </div>
              </div>
              <div>
                <h3 className="text-sm font-medium text-foreground">
                  Long-term conditions
                </h3>
                <div className="mt-1.5 flex flex-wrap gap-1.5">
                  {record.pre_existing_conditions.length > 0 ? (
                    record.pre_existing_conditions.map((condition) => (
                      <Badge key={condition} tone="info">
                        {condition}
                      </Badge>
                    ))
                  ) : (
                    <span className="text-sm text-muted-foreground">None recorded</span>
                  )}
                </div>
              </div>
            </div>
          ) : null}
        </PanelBody>
      </Panel>

      <Panel>
        <PanelHeader
          title="Your visits"
          description={
            record.cases.length > 0
              ? `${record.cases.length} across ${hospitals.size} hospital${hospitals.size === 1 ? "" : "s"}, most recent first`
              : undefined
          }
        />
        {record.cases.length === 0 ? (
          <EmptyState
            icon={FileHeart}
            title="No hospital visits on record"
            description="When a hospital registers you as a patient with your National ID, that visit appears here automatically. Nothing needs to be filed."
          />
        ) : (
          <ul className="divide-y divide-border">
            {record.cases.map((entry) => (
              <li key={entry.case_id}>
                <Visit entry={entry} />
              </li>
            ))}
          </ul>
        )}
      </Panel>
    </div>
  );
}

function Summary({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {label}
      </dt>
      <dd className="mt-1 font-mono text-xl font-semibold tabular-nums text-foreground">
        {value}
      </dd>
    </div>
  );
}

function Visit({ entry }: { entry: PhrCaseEntry }) {
  return (
    <article className="px-4 py-4">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="flex items-center gap-1.5 text-sm font-semibold text-foreground">
            <Building2
              className="size-4 shrink-0 text-muted-foreground"
              strokeWidth={1.75}
              aria-hidden="true"
            />
            {entry.hospital.name}
          </h3>
          <p className="mt-0.5 text-xs text-muted-foreground">
            {entry.hospital.city}, {entry.hospital.state} ·{" "}
            <span className="font-mono">{entry.case_number}</span>
          </p>
        </div>
        <div className="flex items-center gap-2">
          <CaseStatusBadge status={entry.status} />
        </div>
      </header>

      <dl className="mt-3 grid gap-x-6 gap-y-2 text-sm sm:grid-cols-2 lg:grid-cols-4">
        <Line label="Admitted" value={dateTime(entry.admitted_at)} />
        <Line
          label="Discharged"
          value={entry.discharged_at ? dateTime(entry.discharged_at) : "Still admitted"}
        />
        <Line
          label="Length of stay"
          value={stayDuration(entry.admitted_at, entry.discharged_at)}
          mono
        />
        <Line label="Treated by" value={entry.doctor_name ?? "Not recorded"} />
      </dl>

      {entry.case_type_name || entry.chief_symptoms.length > 0 ? (
        <div className="mt-3 flex flex-wrap items-center gap-1.5">
          {entry.case_type_name ? (
            <Badge tone="primary">{entry.case_type_name}</Badge>
          ) : null}
          {entry.chief_symptoms.map((symptom) => (
            <Badge key={symptom} tone="neutral">
              {symptom}
            </Badge>
          ))}
        </div>
      ) : null}

      {entry.discharge_summary ? (
        <div className="mt-3 rounded-md bg-surface-muted px-3 py-2.5">
          <h4 className="flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-muted-foreground">
            <Stethoscope className="size-3.5" strokeWidth={1.75} aria-hidden="true" />
            Discharge summary
          </h4>
          <p className="mt-1 max-w-[70ch] text-sm leading-relaxed text-foreground">
            {entry.discharge_summary}
          </p>
        </div>
      ) : null}

      {entry.prescriptions.length > 0 ? (
        <div className="mt-3">
          <h4 className="flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-muted-foreground">
            <Pill className="size-3.5" strokeWidth={1.75} aria-hidden="true" />
            Prescriptions
          </h4>
          <ul className="mt-1.5 flex flex-col gap-1">
            {entry.prescriptions.map((prescription, index) => (
              <li key={`${prescription.medicine_name}-${index}`} className="text-sm">
                <span className="font-medium text-foreground">
                  {prescription.medicine_name}
                </span>
                <span className="text-muted-foreground">
                  {" "}
                  {prescription.dosage}, {prescription.frequency}, for{" "}
                  {prescription.duration_days} days
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {entry.vitals.length > 0 ? <VitalsTrend vitals={entry.vitals} /> : null}

      {entry.bill ? (
        <div className="mt-3 flex flex-wrap items-center justify-between gap-3 rounded-md border border-border px-3 py-2.5">
          <div>
            <p className="text-sm font-medium text-foreground">
              Invoice <span className="font-mono">{entry.bill.invoice_no}</span>
            </p>
            <p className="mt-0.5 text-xs text-muted-foreground">
              Issued {dateTime(entry.bill.issued_at)}
            </p>
          </div>
          <div className="flex items-center gap-3">
            <p className="text-right">
              <span className="font-mono text-sm font-semibold tabular-nums text-foreground">
                {money(entry.bill.grand_total)}
              </span>
              <span className="block text-xs text-muted-foreground">
                {money(entry.bill.amount_paid)} paid
              </span>
            </p>
            <PaymentBadge status={entry.bill.payment_status} />
          </div>
        </div>
      ) : null}
    </article>
  );
}

/**
 * Vitals are stored as a list rather than a snapshot because deterioration is
 * only visible as a trend, so the citizen sees the whole sequence.
 */
function VitalsTrend({ vitals }: { vitals: VitalSigns[] }) {
  const ordered = [...vitals].sort(
    (a, b) => new Date(a.recorded_at).getTime() - new Date(b.recorded_at).getTime(),
  );

  return (
    <div className="mt-3 overflow-x-auto">
      <table className="w-full min-w-[30rem] text-sm">
        <caption className="pb-1.5 text-left text-xs font-medium uppercase tracking-wide text-muted-foreground">
          Observations recorded during this visit
        </caption>
        <thead className="text-muted-foreground">
          <tr className="border-b border-border">
            <th scope="col" className="pb-1.5 text-left text-xs font-medium">
              Recorded
            </th>
            <th scope="col" className="pb-1.5 text-right text-xs font-medium">
              BP
            </th>
            <th scope="col" className="pb-1.5 text-right text-xs font-medium">
              Pulse
            </th>
            <th scope="col" className="pb-1.5 text-right text-xs font-medium">
              SpO2
            </th>
            <th scope="col" className="pb-1.5 text-right text-xs font-medium">
              Temperature
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {ordered.map((reading, index) => (
            <tr key={`${reading.recorded_at}-${index}`}>
              <td className="py-1.5 text-muted-foreground">{dateTime(reading.recorded_at)}</td>
              <td className="py-1.5 text-right font-mono tabular-nums">
                {reading.systolic_bp}/{reading.diastolic_bp}
              </td>
              <td className="py-1.5 text-right font-mono tabular-nums">
                {reading.pulse_bpm}
              </td>
              <td className="py-1.5 text-right font-mono tabular-nums">
                {reading.spo2_percent}%
              </td>
              <td className="py-1.5 text-right font-mono tabular-nums">
                {reading.temperature_celsius}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Line({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div>
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className={mono ? "font-mono tabular-nums text-foreground" : "text-foreground"}>
        {value}
      </dd>
    </div>
  );
}

export { humanise };
