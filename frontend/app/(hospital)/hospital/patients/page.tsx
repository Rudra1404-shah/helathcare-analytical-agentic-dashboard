import { UserRound } from "lucide-react";
import type { Metadata } from "next";
import { Suspense } from "react";

import { BulkUpload } from "@/app/(hospital)/hospital/patients/bulk-upload";
import { IntakeForm } from "@/app/(hospital)/hospital/patients/intake-form";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/field";
import { PageHeader, Panel, PanelHeader } from "@/components/ui/panel";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/ui/states";
import { Table, TBody, TD, TDMeta, TDPrimary, TH, THead, TR, TableWrap } from "@/components/ui/table";
import { apiTry } from "@/lib/api";
import { humanise, relative } from "@/lib/format";
import { withHospital } from "@/lib/hospital-page";
import type { Paginated, Patient } from "@/lib/types";

export const metadata: Metadata = { title: "Patients" };

export default async function PatientsPage({
  searchParams,
}: {
  searchParams: Promise<{ search?: string }>;
}) {
  const { search } = await searchParams;

  return withHospital("Patients", (hospital) => (
    <>
      <PageHeader
        title="Patients"
        description="This hospital's register. A National ID recorded at intake is encrypted before storage and links the record to the citizen's unified health history, so an encounter here appears in their cross-hospital record without anyone filing paperwork."
      />

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_28rem]">
        <Panel className="order-2 xl:order-1">
          <PanelHeader
            title="Register"
            action={
              <form className="flex items-center gap-2" role="search">
                <label htmlFor="patient-search" className="sr-only">
                  Search by name, MRN, or phone
                </label>
                <Input
                  id="patient-search"
                  name="search"
                  type="search"
                  defaultValue={search ?? ""}
                  placeholder="Name, MRN, or phone"
                  className="h-8 w-56"
                />
                <Button type="submit" size="sm" variant="secondary">
                  Search
                </Button>
              </form>
            }
          />
          <Suspense
            key={search ?? ""}
            fallback={<TableSkeleton rows={8} columns={5} />}
          >
            <PatientTable hospitalId={hospital._id} search={search} />
          </Suspense>
        </Panel>

        <div className="order-1 flex flex-col gap-4 xl:order-2">
          <Panel>
            <IntakeForm hospitalId={hospital._id} />
          </Panel>
          <Panel>
            <BulkUpload hospitalId={hospital._id} />
          </Panel>
        </div>
      </div>
    </>
  ));
}

async function PatientTable({
  hospitalId,
  search,
}: {
  hospitalId: string;
  search?: string;
}) {
  const result = await apiTry<Paginated<Patient>>(`/hospitals/${hospitalId}/patients`, {
    query: { search, limit: 50 },
  });

  if (!result.ok) return <ErrorState message={result.error} />;

  const { items, meta } = result.data;

  if (items.length === 0) {
    return (
      <EmptyState
        icon={UserRound}
        title={search ? "No patients match that search" : "No patients registered yet"}
        description={
          search
            ? "Search matches name, Medical Record Number, and phone number. Clear the search to see the whole register."
            : "Register a patient with the intake form, or import a spreadsheet from your existing system."
        }
      />
    );
  }

  return (
    <>
      <TableWrap>
        <Table className="min-w-[36rem]">
          <THead>
            <tr>
              <TH>Patient</TH>
              <TH>MRN</TH>
              <TH numeric>Age</TH>
              <TH>Blood group</TH>
              <TH>Clinical background</TH>
              <TH>Registered</TH>
            </tr>
          </THead>
          <TBody>
            {items.map((patient) => (
              <TR key={patient._id}>
                <TDPrimary>
                  {patient.full_name}
                  <TDMeta>
                    {humanise(patient.gender)}
                    {patient.phone ? ` · ${patient.phone}` : ""}
                  </TDMeta>
                </TDPrimary>
                <TD>
                  <span className="font-mono text-xs">{patient.mrn}</span>
                  {patient.citizen_user_id ? (
                    <TDMeta>
                      <Badge tone="primary">Linked to citizen</Badge>
                    </TDMeta>
                  ) : null}
                </TD>
                <TD numeric>{patient.age_years ?? "Unknown"}</TD>
                <TD>{patient.blood_group}</TD>
                <TD>
                  <span className="flex flex-wrap gap-1">
                    {patient.allergies.map((allergy) => (
                      <Badge key={allergy} tone="warning">
                        {allergy}
                      </Badge>
                    ))}
                    {patient.pre_existing_conditions.map((condition) => (
                      <Badge key={condition} tone="info">
                        {condition}
                      </Badge>
                    ))}
                    {patient.allergies.length === 0 &&
                    patient.pre_existing_conditions.length === 0 ? (
                      <span className="text-sm text-muted-foreground">None recorded</span>
                    ) : null}
                  </span>
                </TD>
                <TD>{relative(patient.created_at)}</TD>
              </TR>
            ))}
          </TBody>
        </Table>
      </TableWrap>
      <p className="border-t border-border px-4 py-2.5 text-xs text-muted-foreground">
        {meta.total} on the register, showing {items.length}
      </p>
    </>
  );
}
