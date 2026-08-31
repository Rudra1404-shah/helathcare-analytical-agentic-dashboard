import { ClipboardList } from "lucide-react";
import type { Metadata } from "next";
import { Suspense } from "react";

import { Badge, TriageBadge } from "@/components/ui/badge";
import { PageHeader, Panel, PanelHeader } from "@/components/ui/panel";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/ui/states";
import { Table, TBody, TD, TDMeta, TDPrimary, TH, THead, TR, TableWrap } from "@/components/ui/table";
import { apiTry } from "@/lib/api";
import { humanise } from "@/lib/format";
import { CreateCaseTypeDialog } from "@/app/(hospital)/hospital/case-types/case-type-dialog";
import { withHospital } from "@/lib/hospital-page";
import type { CaseType, Paginated } from "@/lib/types";

export const metadata: Metadata = { title: "Case types" };

export default async function CaseTypesPage() {
  return withHospital("Case types", () => (
    <>
      <PageHeader
        title="Case types"
        description="ICD-10 coded conditions with a triage rating. National standards are shared across every hospital; a local definition is scoped to this one. A notifiable type is watched by the outbreak-detection module for anomalous clustering."
        action={<CreateCaseTypeDialog />}
      />
      <Panel>
        <Suspense
          fallback={
            <>
              <PanelHeader title="Available definitions" description="Loading" />
              <TableSkeleton rows={8} columns={5} />
            </>
          }
        >
          <CaseTypeTable />
        </Suspense>
      </Panel>
    </>
  ));
}

async function CaseTypeTable() {
  const result = await apiTry<Paginated<CaseType>>("/case-types", {
    query: { limit: 200 },
  });

  if (!result.ok) {
    return (
      <>
        <PanelHeader title="Available definitions" />
        <ErrorState message={result.error} />
      </>
    );
  }

  const { items, meta } = result.data;

  if (items.length === 0) {
    return (
      <>
        <PanelHeader title="Available definitions" />
        <EmptyState
          icon={ClipboardList}
          title="No case types defined"
          description="Define a case type before classifying an admission. A case with no classification cannot feed outbreak detection."
        />
      </>
    );
  }

  const notifiable = items.filter((item) => item.is_notifiable).length;

  return (
    <>
      <PanelHeader
        title="Available definitions"
        description={`${meta.total} available, ${notifiable} notifiable to the ministry`}
      />
      <TableWrap>
        <Table>
          <THead>
            <tr>
              <TH>Condition</TH>
              <TH>ICD-10</TH>
              <TH>Category</TH>
              <TH>Triage</TH>
              <TH>Scope</TH>
            </tr>
          </THead>
          <TBody>
            {items.map((caseType) => (
              <TR key={caseType._id}>
                <TDPrimary>
                  {caseType.name}
                  {caseType.description ? <TDMeta>{caseType.description}</TDMeta> : null}
                </TDPrimary>
                <TD>
                  <span className="font-mono text-xs">{caseType.icd10_code}</span>
                </TD>
                <TD>{humanise(caseType.disease_category)}</TD>
                <TD>
                  <TriageBadge level={caseType.triage_level} />
                </TD>
                <TD>
                  <span className="flex flex-wrap gap-1">
                    <Badge tone={caseType.hospital_id === null ? "primary" : "neutral"}>
                      {caseType.hospital_id === null ? "National standard" : "This hospital"}
                    </Badge>
                    {caseType.is_notifiable ? <Badge tone="warning">Notifiable</Badge> : null}
                  </span>
                </TD>
              </TR>
            ))}
          </TBody>
        </Table>
      </TableWrap>
    </>
  );
}
