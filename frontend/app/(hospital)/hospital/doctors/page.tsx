import { Stethoscope } from "lucide-react";
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
import { DoctorIntakeTrigger } from "@/components/data/workforce-triggers";
import { withHospital } from "@/lib/hospital-page";
import type { Department, Doctor, Paginated, ShiftType } from "@/lib/types";

export const metadata: Metadata = { title: "Doctors" };

const SHIFTS: ShiftType[] = ["MORNING", "EVENING", "NIGHT", "GENERAL"];

export default async function DoctorsPage({
  searchParams,
}: {
  searchParams: Promise<{ shift?: ShiftType; department_id?: string }>;
}) {
  const filters = await searchParams;

  return withHospital("Doctors", (hospital) => (
    <>
      <PageHeader
        title="Doctors"
        description="Onboarded physicians, their specialisations, and the daily patient cap each one carries. That cap is what the workforce-reallocation module reads when deciding whether a department is over-subscribed."
        action={
          <Suspense fallback={<div className="skeleton h-8 w-40 rounded-md" />}>
            <DoctorIntakeTrigger hospitalId={hospital._id} />
          </Suspense>
        }
      />

      <Suspense fallback={<div className="skeleton h-14 rounded-lg" />}>
        <DoctorFilters hospitalId={hospital._id} current={filters} />
      </Suspense>

      <Panel className="mt-4">
        <Suspense
          key={JSON.stringify(filters)}
          fallback={
            <>
              <PanelHeader title="Roster" description="Loading" />
              <TableSkeleton rows={8} columns={5} />
            </>
          }
        >
          <DoctorTable hospitalId={hospital._id} filters={filters} />
        </Suspense>
      </Panel>
    </>
  ));
}

async function DoctorFilters({
  hospitalId,
  current,
}: {
  hospitalId: string;
  current: { shift?: string; department_id?: string };
}) {
  const departments = await apiTry<Paginated<Department>>(
    `/hospitals/${hospitalId}/departments`,
    { query: { limit: 100 } },
  );

  return (
    <Panel className="p-3">
      <form className="flex flex-wrap items-end gap-3">
        <FilterSelect
          label="Department"
          name="department_id"
          defaultValue={current.department_id ?? ""}
        >
          <option value="">All departments</option>
          {departments.ok
            ? departments.data.items.map((department) => (
                <option key={department._id} value={department._id}>
                  {department.name}
                </option>
              ))
            : null}
        </FilterSelect>

        <FilterSelect label="Shift" name="shift" defaultValue={current.shift ?? ""}>
          <option value="">All shifts</option>
          {SHIFTS.map((shift) => (
            <option key={shift} value={shift}>
              {humanise(shift)}
            </option>
          ))}
        </FilterSelect>

        <Button type="submit" size="sm">
          Apply
        </Button>
      </form>
    </Panel>
  );
}

async function DoctorTable({
  hospitalId,
  filters,
}: {
  hospitalId: string;
  filters: { shift?: ShiftType; department_id?: string };
}) {
  const [doctors, departments] = await Promise.all([
    apiTry<Paginated<Doctor>>(`/hospitals/${hospitalId}/doctors`, {
      query: { shift: filters.shift, department_id: filters.department_id, limit: 100 },
    }),
    apiTry<Paginated<Department>>(`/hospitals/${hospitalId}/departments`, {
      query: { limit: 100 },
    }),
  ]);

  if (!doctors.ok) {
    return (
      <>
        <PanelHeader title="Roster" />
        <ErrorState message={doctors.error} />
      </>
    );
  }

  const departmentName = new Map(
    departments.ok ? departments.data.items.map((item) => [item._id, item.name]) : [],
  );

  const { items, meta } = doctors.data;

  if (items.length === 0) {
    return (
      <>
        <PanelHeader title="Roster" />
        <EmptyState
          icon={Stethoscope}
          title="No doctors match these filters"
          description="Onboard a doctor through the Doctor Onboarding form. A medical council licence is unique across the whole platform, not just this hospital."
        />
      </>
    );
  }

  return (
    <>
      <PanelHeader title="Roster" description={`${meta.total} onboarded`} />
      <TableWrap>
        <Table>
          <THead>
            <tr>
              <TH>Doctor</TH>
              <TH>Specialisation</TH>
              <TH>Department</TH>
              <TH>Shifts</TH>
              <TH numeric>Daily cap</TH>
              <TH>Status</TH>
            </tr>
          </THead>
          <TBody>
            {items.map((doctor) => (
              <TR key={doctor._id}>
                <TDPrimary>
                  {doctor.full_name}
                  <TDMeta>
                    <span className="font-mono">{doctor.license_no}</span> ·{" "}
                    {doctor.qualification}
                  </TDMeta>
                </TDPrimary>
                <TD>{doctor.specialization}</TD>
                <TD>{departmentName.get(doctor.department_id) ?? "Unassigned"}</TD>
                <TD>
                  <span className="flex flex-wrap gap-1">
                    {doctor.shifts.map((shift) => (
                      <Badge key={shift} tone="neutral">
                        {humanise(shift)}
                      </Badge>
                    ))}
                    {doctor.is_emergency_on_call ? (
                      <Badge tone="warning">On call</Badge>
                    ) : null}
                  </span>
                </TD>
                <TD numeric>{doctor.max_daily_patients}</TD>
                <TD>
                  <StaffStatusBadge status={doctor.status} />
                </TD>
              </TR>
            ))}
          </TBody>
        </Table>
      </TableWrap>
    </>
  );
}
