import { MessageSquareWarning } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { InvestigationBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { FilterSelect } from "@/components/ui/field";
import { PageHeader, Panel, PanelHeader } from "@/components/ui/panel";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/ui/states";
import { Table, TBody, TD, TDMeta, TDPrimary, TH, THead, TR, TableWrap } from "@/components/ui/table";
import { apiTry } from "@/lib/api";
import { dateOnly, humanise, relative } from "@/lib/format";
import type {
  Complaint,
  ComplaintCategory,
  Hospital,
  InvestigationStatus,
  Paginated,
} from "@/lib/types";

export const metadata: Metadata = { title: "Complaints desk" };

const CATEGORIES: ComplaintCategory[] = [
  "OVERCHARGING",
  "BED_REFUSAL",
  "NEGLIGENCE",
  "HYGIENE",
  "SHORTAGE",
  "FALSE_BILLING",
];

const STATUSES: InvestigationStatus[] = [
  "SUBMITTED",
  "UNDER_REVIEW",
  "INQUIRY_ASSIGNED",
  "ACTION_TAKEN",
  "DISMISSED",
];

interface Filters {
  category?: ComplaintCategory;
  investigation_status?: InvestigationStatus;
  open_only?: string;
}

export default async function ComplaintsDeskPage({
  searchParams,
}: {
  searchParams: Promise<Filters>;
}) {
  const filters = await searchParams;

  return (
    <>
      <PageHeader
        title="Complaints desk"
        description="Citizen grievances filed against registered hospitals. Every complaint carries mandatory photographic or video evidence, and closing an investigation requires both a recorded action and the reasoning behind it."
      />

      <Panel className="p-3">
        <form className="flex flex-wrap items-end gap-3">
          <FilterSelect
            label="Category"
            name="category"
            defaultValue={filters.category ?? ""}
          >
            <option value="">All categories</option>
            {CATEGORIES.map((category) => (
              <option key={category} value={category}>
                {humanise(category)}
              </option>
            ))}
          </FilterSelect>

          <FilterSelect
            label="Investigation"
            name="investigation_status"
            defaultValue={filters.investigation_status ?? ""}
          >
            <option value="">Any status</option>
            {STATUSES.map((status) => (
              <option key={status} value={status}>
                {humanise(status)}
              </option>
            ))}
          </FilterSelect>

          <FilterSelect
            label="Scope"
            name="open_only"
            defaultValue={filters.open_only ?? ""}
          >
            <option value="">Everything</option>
            <option value="true">Open investigations only</option>
          </FilterSelect>

          <Button type="submit" size="sm">
            Apply
          </Button>
        </form>
      </Panel>

      <Panel className="mt-4">
        <Suspense key={JSON.stringify(filters)} fallback={<DeskSkeleton />}>
          <ComplaintsTable filters={filters} />
        </Suspense>
      </Panel>
    </>
  );
}

function DeskSkeleton() {
  return (
    <>
      <PanelHeader title="Filed complaints" description="Loading" />
      <TableSkeleton rows={6} columns={6} />
    </>
  );
}

async function ComplaintsTable({ filters }: { filters: Filters }) {
  const [complaints, hospitals] = await Promise.all([
    apiTry<Paginated<Complaint>>("/complaints", {
      query: {
        category: filters.category,
        investigation_status: filters.investigation_status,
        open_only: filters.open_only === "true" ? true : undefined,
        limit: 50,
      },
    }),
    apiTry<Paginated<Hospital>>("/hospitals", { query: { limit: 200 } }),
  ]);

  if (!complaints.ok) {
    return (
      <>
        <PanelHeader title="Filed complaints" />
        <ErrorState message={complaints.error} />
      </>
    );
  }

  const nameFor = new Map(
    hospitals.ok ? hospitals.data.items.map((item) => [item._id, item.name]) : [],
  );

  const { items, meta } = complaints.data;

  if (items.length === 0) {
    return (
      <>
        <PanelHeader title="Filed complaints" />
        <EmptyState
          icon={MessageSquareWarning}
          title="No complaints match these filters"
          description="Nothing has been filed under this combination. Clear the filters to see every grievance on the platform."
        />
      </>
    );
  }

  return (
    <>
      <PanelHeader
        title="Filed complaints"
        description={`${meta.total} filed, showing ${items.length}`}
      />
      <TableWrap>
        <Table>
          <THead>
            <tr>
              <TH>Reference</TH>
              <TH>Hospital</TH>
              <TH>Category</TH>
              <TH>Incident</TH>
              <TH numeric>Evidence</TH>
              <TH>Investigation</TH>
              <TH className="text-right">Action</TH>
            </tr>
          </THead>
          <TBody>
            {items.map((complaint) => (
              <TR key={complaint._id}>
                <TDPrimary>
                  <span className="font-mono text-xs">{complaint.complaint_number}</span>
                  <TDMeta>Filed {relative(complaint.created_at)}</TDMeta>
                </TDPrimary>
                <TD>{nameFor.get(complaint.hospital_id) ?? "Unknown hospital"}</TD>
                <TD>{humanise(complaint.category)}</TD>
                <TD>{dateOnly(complaint.incident_at)}</TD>
                <TD numeric>{complaint.evidence.length}</TD>
                <TD>
                  <InvestigationBadge status={complaint.investigation_status} />
                </TD>
                <TD className="text-right">
                  <Button asChild variant="ghost" size="sm">
                    <Link href={`/gov/complaints/${complaint._id}`}>Investigate</Link>
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
