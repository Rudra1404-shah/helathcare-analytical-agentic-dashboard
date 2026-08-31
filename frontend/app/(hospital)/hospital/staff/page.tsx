import { Users } from "lucide-react";
import type { Metadata } from "next";
import { Suspense } from "react";

import { Badge, StaffStatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { FilterSelect } from "@/components/ui/field";
import { PageHeader, Panel, PanelHeader } from "@/components/ui/panel";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/ui/states";
import { Table, TBody, TD, TDMeta, TDPrimary, TH, THead, TR, TableWrap } from "@/components/ui/table";
import { apiTry } from "@/lib/api";
import { humanise } from "@/lib/format";
import { StaffIntakeTrigger } from "@/components/data/workforce-triggers";
import { withHospital } from "@/lib/hospital-page";
import type { Paginated, ShiftType, Staff, StaffCategory } from "@/lib/types";

export const metadata: Metadata = { title: "Staff roster" };

const SHIFTS: ShiftType[] = ["MORNING", "EVENING", "NIGHT", "GENERAL"];
const CATEGORIES: StaffCategory[] = ["MEDICAL", "ADMIN_SUPPORT"];

interface Filters {
  shift?: ShiftType;
  staff_category?: StaffCategory;
  view?: string;
}

export default async function StaffPage({
  searchParams,
}: {
  searchParams: Promise<Filters>;
}) {
  const filters = await searchParams;

  return withHospital("Staff roster", (hospital) => (
    <>
      <PageHeader
        title="Staff roster"
        description="Admin, support, and medical staff. Both intake forms resolve to one register, discriminated by category, so clinical headcount can never be inflated by a support role filed on the wrong form."
        action={
          <Suspense fallback={<div className="skeleton h-8 w-40 rounded-md" />}>
            <StaffIntakeTrigger hospitalId={hospital._id} />
          </Suspense>
        }
      />

      <Panel className="p-3">
        <form className="flex flex-wrap items-end gap-3">
          <FilterSelect label="Shift" name="shift" defaultValue={filters.shift ?? ""}>
            <option value="">All shifts</option>
            {SHIFTS.map((shift) => (
              <option key={shift} value={shift}>
                {humanise(shift)}
              </option>
            ))}
          </FilterSelect>

          <FilterSelect
            label="Category"
            name="staff_category"
            defaultValue={filters.staff_category ?? ""}
          >
            <option value="">All staff</option>
            {CATEGORIES.map((category) => (
              <option key={category} value={category}>
                {humanise(category)}
              </option>
            ))}
          </FilterSelect>

          <FilterSelect label="Arrangement" name="view" defaultValue={filters.view ?? ""}>
            <option value="">Flat register</option>
            <option value="hierarchy">By seniority</option>
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
              <PanelHeader title="Workforce" description="Loading" />
              <TableSkeleton rows={8} columns={5} />
            </>
          }
        >
          {filters.view === "hierarchy" ? (
            <Hierarchy hospitalId={hospital._id} shift={filters.shift} />
          ) : (
            <Register hospitalId={hospital._id} filters={filters} />
          )}
        </Suspense>
      </Panel>
    </>
  ));
}

async function Register({
  hospitalId,
  filters,
}: {
  hospitalId: string;
  filters: Filters;
}) {
  const result = await apiTry<Paginated<Staff>>(`/hospitals/${hospitalId}/staff`, {
    query: { shift: filters.shift, staff_category: filters.staff_category, limit: 100 },
  });

  if (!result.ok) {
    return (
      <>
        <PanelHeader title="Workforce" />
        <ErrorState message={result.error} />
      </>
    );
  }

  const { items, meta } = result.data;

  if (items.length === 0) {
    return (
      <>
        <PanelHeader title="Workforce" />
        <EmptyState
          icon={Users}
          title="No staff match these filters"
          description="File an Admin and Support or Medical intake form to add someone to the register, or clear the filters to see everyone."
        />
      </>
    );
  }

  return (
    <>
      <PanelHeader title="Workforce" description={`${meta.total} on the register`} />
      <TableWrap>
        <Table>
          <THead>
            <tr>
              <TH>Name</TH>
              <TH>Role</TH>
              <TH>Shift</TH>
              <TH>Registration</TH>
              <TH>Status</TH>
            </tr>
          </THead>
          <TBody>
            {items.map((member) => (
              <TR key={member._id}>
                <TDPrimary>
                  {member.full_name}
                  <TDMeta>
                    <span className="font-mono">{member.employee_id}</span> · {member.phone}
                  </TDMeta>
                </TDPrimary>
                <TD>
                  {humanise(member.role)}
                  <TDMeta>{humanise(member.staff_category)}</TDMeta>
                </TD>
                <TD>
                  {humanise(member.shift)}
                  {member.is_emergency_on_call ? (
                    <TDMeta>
                      <Badge tone="warning">On call</Badge>
                    </TDMeta>
                  ) : null}
                </TD>
                <TD>
                  {member.registration_no ? (
                    <span className="font-mono text-xs">{member.registration_no}</span>
                  ) : (
                    <span className="text-muted-foreground">Not applicable</span>
                  )}
                </TD>
                <TD>
                  <StaffStatusBadge status={member.status} />
                </TD>
              </TR>
            ))}
          </TBody>
        </Table>
      </TableWrap>
    </>
  );
}

async function Hierarchy({
  hospitalId,
  shift,
}: {
  hospitalId: string;
  shift?: ShiftType;
}) {
  const result = await apiTry<Record<string, Staff[]>>(
    `/hospitals/${hospitalId}/staff/hierarchy`,
    { query: { shift } },
  );

  if (!result.ok) {
    return (
      <>
        <PanelHeader title="Chain of command" />
        <ErrorState message={result.error} />
      </>
    );
  }

  const groups = Object.entries(result.data);

  if (groups.length === 0) {
    return (
      <>
        <PanelHeader title="Chain of command" />
        <EmptyState
          icon={Users}
          title="Nobody is active on this shift"
          description="The hierarchy shows only active staff. Choose a different shift, or check the flat register for staff on leave."
        />
      </>
    );
  }

  return (
    <>
      <PanelHeader
        title="Chain of command"
        description="Clinical roles first, then administrative, then support."
      />
      <div className="divide-y divide-border">
        {groups.map(([role, members]) => (
          <section key={role} className="px-4 py-3">
            <h3 className="flex items-baseline gap-2 text-sm font-medium text-foreground">
              {humanise(role)}
              <span className="font-mono text-xs tabular-nums text-muted-foreground">
                {members.length}
              </span>
            </h3>
            <ul className="mt-2 flex flex-wrap gap-2">
              {members.map((member) => (
                <li
                  key={member._id}
                  className="rounded-md border border-border px-2.5 py-1.5 text-sm"
                >
                  {member.full_name}
                  <span className="ml-2 font-mono text-xs text-muted-foreground">
                    {humanise(member.shift)}
                  </span>
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>
    </>
  );
}
