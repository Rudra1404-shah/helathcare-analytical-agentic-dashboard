import { ArrowLeft } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";

import { PrintButton } from "@/app/(hospital)/hospital/bills/[billId]/print-button";
import { PaymentBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Panel } from "@/components/ui/panel";
import { ErrorState } from "@/components/ui/states";
import { apiTry } from "@/lib/api";
import { dateTime, humanise, money } from "@/lib/format";
import type { Bill, Hospital, Patient, PatientCase } from "@/lib/types";

export const metadata: Metadata = { title: "Receipt" };

export default async function ReceiptPage({
  params,
}: {
  params: Promise<{ billId: string }>;
}) {
  const { billId } = await params;
  const result = await apiTry<Bill>(`/bills/${billId}`);

  if (!result.ok) {
    return (
      <Panel className="mt-4">
        <ErrorState message={result.error} />
      </Panel>
    );
  }

  const bill = result.data;
  const [hospital, patient, patientCase] = await Promise.all([
    apiTry<Hospital>(`/hospitals/${bill.hospital_id}`),
    apiTry<Patient>(`/patients/${bill.patient_id}`),
    apiTry<PatientCase>(`/cases/${bill.case_id}`),
  ]);

  const outstanding = (() => {
    // Both are exact decimal strings from the API. Subtracting them here would
    // reintroduce float arithmetic, so the paid and total figures are shown
    // side by side and the reader does the comparison.
    return bill.amount_paid !== bill.grand_total;
  })();

  return (
    <>
      <div className="no-print mb-1 flex items-center justify-between gap-3">
        <Button asChild variant="ghost" size="sm" className="-ml-3">
          <Link href="/hospital/bills">
            <ArrowLeft strokeWidth={1.75} aria-hidden="true" />
            Billing
          </Link>
        </Button>
        <PrintButton />
      </div>

      <Panel className="print-sheet mx-auto max-w-3xl p-8">
        <header className="flex flex-wrap items-start justify-between gap-4 border-b border-border pb-5">
          <div>
            <h1 className="text-lg font-semibold tracking-tight text-foreground">
              {hospital.ok ? hospital.data.name : "Hospital"}
            </h1>
            {hospital.ok ? (
              <p className="mt-0.5 text-sm text-muted-foreground">
                {hospital.data.ward_area ? `${hospital.data.ward_area}, ` : ""}
                {hospital.data.city}, {hospital.data.state}
                <br />
                Licence <span className="font-mono">{hospital.data.license_no}</span>
              </p>
            ) : null}
          </div>
          <div className="text-right">
            <p className="text-sm font-medium text-foreground">Tax invoice</p>
            <p className="mt-0.5 font-mono text-sm text-foreground">{bill.invoice_no}</p>
            <p className="mt-0.5 text-xs text-muted-foreground">
              Issued {dateTime(bill.issued_at)}
            </p>
            <div className="mt-2 flex justify-end">
              <PaymentBadge status={bill.payment_status} />
            </div>
          </div>
        </header>

        <section className="grid gap-6 border-b border-border py-5 sm:grid-cols-2">
          <div>
            <h2 className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Billed to
            </h2>
            <p className="mt-1.5 text-sm font-medium text-foreground">
              {patient.ok ? patient.data.full_name : "Patient record not visible"}
            </p>
            {patient.ok ? (
              <p className="mt-0.5 text-sm text-muted-foreground">
                MRN <span className="font-mono">{patient.data.mrn}</span>
                {patient.data.phone ? (
                  <>
                    <br />
                    {patient.data.phone}
                  </>
                ) : null}
              </p>
            ) : null}
          </div>

          <div>
            <h2 className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              For treatment under
            </h2>
            {patientCase.ok ? (
              <>
                <p className="mt-1.5 font-mono text-sm font-medium text-foreground">
                  {patientCase.data.case_number}
                </p>
                <p className="mt-0.5 text-sm text-muted-foreground">
                  Admitted {dateTime(patientCase.data.admitted_at)}
                  <br />
                  {patientCase.data.discharged_at
                    ? `Discharged ${dateTime(patientCase.data.discharged_at)}`
                    : humanise(patientCase.data.status)}
                </p>
              </>
            ) : (
              <p className="mt-1.5 text-sm text-muted-foreground">Case not visible.</p>
            )}
          </div>
        </section>

        <table className="mt-5 w-full text-sm">
          <caption className="sr-only">
            Itemised charges for invoice {bill.invoice_no}
          </caption>
          <thead>
            <tr className="border-b border-border text-muted-foreground">
              <th scope="col" className="pb-2 text-left text-xs font-medium uppercase tracking-wide">
                Description
              </th>
              <th scope="col" className="pb-2 text-right text-xs font-medium uppercase tracking-wide">
                Rate
              </th>
              <th scope="col" className="pb-2 text-right text-xs font-medium uppercase tracking-wide">
                Quantity
              </th>
              <th scope="col" className="pb-2 text-right text-xs font-medium uppercase tracking-wide">
                Amount
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {bill.line_items.map((line, index) => (
              <tr key={`${line.description}-${index}`}>
                <td className="py-2.5 text-foreground">{line.description}</td>
                <td className="py-2.5 text-right font-mono tabular-nums">
                  {money(line.rate)}
                </td>
                <td className="py-2.5 text-right font-mono tabular-nums">{line.quantity}</td>
                <td className="py-2.5 text-right font-mono tabular-nums">
                  {money(line.total)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        <dl className="mt-5 ml-auto w-full max-w-xs space-y-1.5 text-sm">
          <Row label="Subtotal" value={money(bill.subtotal)} />
          <Row label="Tax" value={money(bill.tax_amount)} />
          <Row label="Discount" value={`- ${money(bill.discount_amount)}`} />
          <div className="border-t border-border pt-1.5">
            <Row label="Grand total" value={money(bill.grand_total)} emphasis />
          </div>
          <Row label="Paid" value={money(bill.amount_paid)} />
          {outstanding ? (
            <Row
              label="Outstanding"
              value={`${money(bill.grand_total)} less ${money(bill.amount_paid)}`}
              tone="critical"
            />
          ) : null}
        </dl>

        <footer className="mt-6 border-t border-border pt-4 text-xs text-muted-foreground">
          {bill.payment_mode ? (
            <p>Settled by {humanise(bill.payment_mode).toLowerCase()}.</p>
          ) : null}
          {bill.settled_at ? <p>Payment completed {dateTime(bill.settled_at)}.</p> : null}
          <p className="mt-2">
            Amounts are exact. This invoice is issued through the Unified National Health
            Platform and is auditable against case {patientCase.ok ? patientCase.data.case_number : bill.case_id}.
          </p>
        </footer>
      </Panel>
    </>
  );
}

function Row({
  label,
  value,
  emphasis,
  tone,
}: {
  label: string;
  value: string;
  emphasis?: boolean;
  tone?: "critical";
}) {
  return (
    <div className="flex items-baseline justify-between gap-4">
      <dt
        className={
          emphasis
            ? "font-medium text-foreground"
            : tone === "critical"
              ? "text-critical"
              : "text-muted-foreground"
        }
      >
        {label}
      </dt>
      <dd
        className={
          emphasis
            ? "font-mono text-base font-semibold tabular-nums text-foreground"
            : tone === "critical"
              ? "font-mono tabular-nums text-critical"
              : "font-mono tabular-nums text-foreground"
        }
      >
        {value}
      </dd>
    </div>
  );
}
