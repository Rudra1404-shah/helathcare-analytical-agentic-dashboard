import { Receipt } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { PaymentBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { FilterSelect } from "@/components/ui/field";
import { PageHeader, Panel, PanelHeader } from "@/components/ui/panel";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/ui/states";
import { Table, TBody, TD, TDMeta, TDPrimary, TH, THead, TR, TableWrap } from "@/components/ui/table";
import { apiTry } from "@/lib/api";
import { dateOnly, money } from "@/lib/format";
import { withHospital } from "@/lib/hospital-page";
import type { Bill, Paginated, Patient, PaymentStatus } from "@/lib/types";

export const metadata: Metadata = { title: "Billing" };

const STATUSES: PaymentStatus[] = [
  "PENDING",
  "PARTIALLY_PAID",
  "PAID",
  "CANCELLED",
  "REFUNDED",
];

export default async function BillsPage({
  searchParams,
}: {
  searchParams: Promise<{ payment_status?: PaymentStatus }>;
}) {
  const filters = await searchParams;

  return withHospital("Billing", (hospital) => (
    <>
      <PageHeader
        title="Billing"
        description="Itemised invoices raised against closed cases. Line totals, subtotal, and grand total are all computed server-side from rates and quantities, so an overcharging complaint can never be a rounding bug in disguise."
      />

      <Panel className="p-3">
        <form className="flex flex-wrap items-end gap-3">
          <FilterSelect
            label="Payment status"
            name="payment_status"
            defaultValue={filters.payment_status ?? ""}
          >
            <option value="">Any status</option>
            {STATUSES.map((status) => (
              <option key={status} value={status}>
                {status.charAt(0) + status.slice(1).toLowerCase().replace(/_/g, " ")}
              </option>
            ))}
          </FilterSelect>
          <Button type="submit" size="sm">
            Apply
          </Button>
        </form>
      </Panel>

      <Panel className="mt-4">
        <Suspense
          key={JSON.stringify(filters)}
          fallback={
            <>
              <PanelHeader title="Invoices" description="Loading" />
              <TableSkeleton rows={8} columns={6} />
            </>
          }
        >
          <BillsTable hospitalId={hospital._id} status={filters.payment_status} />
        </Suspense>
      </Panel>
    </>
  ));
}

async function BillsTable({
  hospitalId,
  status,
}: {
  hospitalId: string;
  status?: PaymentStatus;
}) {
  const [bills, patients] = await Promise.all([
    apiTry<Paginated<Bill>>(`/hospitals/${hospitalId}/bills`, {
      query: { payment_status: status, limit: 100 },
    }),
    apiTry<Paginated<Patient>>(`/hospitals/${hospitalId}/patients`, {
      query: { limit: 200 },
    }),
  ]);

  if (!bills.ok) {
    return (
      <>
        <PanelHeader title="Invoices" />
        <ErrorState message={bills.error} />
      </>
    );
  }

  const patientName = new Map(
    patients.ok ? patients.data.items.map((item) => [item._id, item.full_name]) : [],
  );

  const { items, meta } = bills.data;

  if (items.length === 0) {
    return (
      <>
        <PanelHeader title="Invoices" />
        <EmptyState
          icon={Receipt}
          title="No invoices match this filter"
          description="Raise an invoice against a case to bill for it. An invoice must charge for at least one thing."
        />
      </>
    );
  }

  return (
    <>
      <PanelHeader title="Invoices" description={`${meta.total} issued`} />
      <TableWrap>
        <Table>
          <THead>
            <tr>
              <TH>Invoice</TH>
              <TH>Patient</TH>
              <TH numeric>Lines</TH>
              <TH numeric>Grand total</TH>
              <TH numeric>Paid</TH>
              <TH>Status</TH>
              <TH className="text-right">Receipt</TH>
            </tr>
          </THead>
          <TBody>
            {items.map((bill) => (
              <TR key={bill._id}>
                <TDPrimary>
                  <span className="font-mono text-xs">{bill.invoice_no}</span>
                  <TDMeta>Issued {dateOnly(bill.issued_at)}</TDMeta>
                </TDPrimary>
                <TD>{patientName.get(bill.patient_id) ?? "Record not visible"}</TD>
                <TD numeric>{bill.line_items.length}</TD>
                <TD numeric>{money(bill.grand_total)}</TD>
                <TD numeric>{money(bill.amount_paid)}</TD>
                <TD>
                  <PaymentBadge status={bill.payment_status} />
                </TD>
                <TD className="text-right">
                  <Button asChild variant="ghost" size="sm">
                    <Link href={`/hospital/bills/${bill._id}`}>View</Link>
                  </Button>
                </TD>
              </TR>
            ))}
          </TBody>
        </Table>
      </TableWrap>
    </>
  );
}
