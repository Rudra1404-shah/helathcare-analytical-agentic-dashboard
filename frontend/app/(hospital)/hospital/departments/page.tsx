import { Bed } from "lucide-react";
import type { Metadata } from "next";
import { Suspense } from "react";

import { Badge } from "@/components/ui/badge";
import { PageHeader, Panel, PanelHeader } from "@/components/ui/panel";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/ui/states";
import { Table, TBody, TD, TDMeta, TDPrimary, TH, THead, TR, TableWrap } from "@/components/ui/table";
import { apiTry } from "@/lib/api";
import { DepartmentCreateTrigger } from "@/components/data/workforce-triggers";
import { withHospital } from "@/lib/hospital-page";
import type { Department, Doctor, Paginated } from "@/lib/types";

export const metadata: Metadata = { title: "Departments" };

export default async function DepartmentsPage() {
  return withHospital("Departments", (hospital) => (
    <>
      <PageHeader
        title="Departments"
        description="The clinical unit registry. Department codes are unique within this hospital, not across the platform, so two hospitals may both run a unit coded CARD."
        action={
          <Suspense fallback={<div className="skeleton h-8 w-40 rounded-md" />}>
            <DepartmentCreateTrigger hospitalId={hospital._id} />
          </Suspense>
        }
      />
      <Panel>
        <Suspense
          fallback={
            <>
              <PanelHeader title="Registered departments" description="Loading" />
              <TableSkeleton rows={5} columns={5} />
            </>
          }
        >
          <DepartmentTable hospitalId={hospital._id} />
        </Suspense>
      </Panel>
    </>
  ));
}

async function DepartmentTable({ hospitalId }: { hospitalId: string }) {
  const [departments, doctors] = await Promise.all([
    apiTry<Paginated<Department>>(`/hospitals/${hospitalId}/departments`, {
      query: { limit: 100 },
    }),
    apiTry<Paginated<Doctor>>(`/hospitals/${hospitalId}/doctors`, { query: { limit: 200 } }),
  ]);

  if (!departments.ok) {
    return (
      <>
        <PanelHeader title="Registered departments" />
        <ErrorState message={departments.error} />
      </>
    );
  }

  const doctorName = new Map(
    doctors.ok ? doctors.data.items.map((item) => [item._id, item.full_name]) : [],
  );
  const headcount = new Map<string, number>();
  if (doctors.ok) {
    for (const doctor of doctors.data.items) {
      headcount.set(doctor.department_id, (headcount.get(doctor.department_id) ?? 0) + 1);
    }
  }

  const { items, meta } = departments.data;

  if (items.length === 0) {
    return (
      <>
        <PanelHeader title="Registered departments" />
        <EmptyState
          icon={Bed}
          title="No departments registered"
          description="Register a department before onboarding doctors or admitting patients. Cases must name the department treating them."
        />
      </>
    );
  }

  return (
    <>
      <PanelHeader title="Registered departments" description={`${meta.total} registered`} />
      <TableWrap>
        <Table>
          <THead>
            <tr>
              <TH>Department</TH>
              <TH>Location</TH>
              <TH>Head of department</TH>
              <TH numeric>Beds</TH>
              <TH numeric>Doctors</TH>
              <TH>Status</TH>
            </tr>
          </THead>
          <TBody>
            {items.map((department) => (
              <TR key={department._id}>
                <TDPrimary>
                  {department.name}
                  <TDMeta>
                    <span className="font-mono">{department.code}</span>
                  </TDMeta>
                </TDPrimary>
                <TD>
                  {department.wing ? `${department.wing} wing` : "Not recorded"}
                  <TDMeta>
                    {department.floor ? `Floor ${department.floor}` : "Floor not recorded"}
                  </TDMeta>
                </TD>
                <TD>
                  {department.hod_doctor_id
                    ? (doctorName.get(department.hod_doctor_id) ?? "Assigned")
                    : "Not appointed"}
                </TD>
                <TD numeric>{department.bed_count}</TD>
                <TD numeric>{headcount.get(department._id) ?? 0}</TD>
                <TD>
                  <Badge tone={department.is_active ? "stable" : "neutral"}>
                    {department.is_active ? "Active" : "Inactive"}
                  </Badge>
                </TD>
              </TR>
            ))}
          </TBody>
        </Table>
      </TableWrap>
    </>
  );
}
