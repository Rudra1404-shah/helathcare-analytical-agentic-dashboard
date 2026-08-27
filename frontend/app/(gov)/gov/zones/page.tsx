import { Map } from "lucide-react";
import type { Metadata } from "next";
import { Suspense } from "react";

import { Badge } from "@/components/ui/badge";
import { PageHeader, Panel, PanelHeader } from "@/components/ui/panel";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/ui/states";
import { Table, TBody, TD, TDMeta, TDPrimary, TH, THead, TR, TableWrap } from "@/components/ui/table";
import { apiTry } from "@/lib/api";
import type { Paginated, Zone } from "@/lib/types";

export const metadata: Metadata = { title: "Zones and areas" };

export default function ZonesPage() {
  return (
    <>
      <PageHeader
        title="Zones and areas"
        description="Administrative areas and the census population each one serves. Population is the denominator the outbreak-detection and surge-forecasting modules divide by, which is why a hospital cannot be registered against an unknown zone."
      />
      <Panel>
        <Suspense
          fallback={
            <>
              <PanelHeader title="Registered zones" description="Loading" />
              <TableSkeleton rows={6} columns={4} />
            </>
          }
        >
          <ZonesTable />
        </Suspense>
      </Panel>
    </>
  );
}

async function ZonesTable() {
  const result = await apiTry<Paginated<Zone>>("/zones", { query: { limit: 100 } });

  if (!result.ok) {
    return (
      <>
        <PanelHeader title="Registered zones" />
        <ErrorState message={result.error} />
      </>
    );
  }

  const { items, meta } = result.data;

  if (items.length === 0) {
    return (
      <>
        <PanelHeader title="Registered zones" />
        <EmptyState
          icon={Map}
          title="No zones registered yet"
          description="Register a zone before onboarding hospitals into it. Without a population figure, per-capita outbreak and surge analytics cannot be computed for that area."
        />
      </>
    );
  }

  return (
    <>
      <PanelHeader title="Registered zones" description={`${meta.total} on the register`} />
      <TableWrap>
        <Table>
          <THead>
            <tr>
              <TH>Zone</TH>
              <TH>City</TH>
              <TH numeric>Population covered</TH>
              <TH>Status</TH>
            </tr>
          </THead>
          <TBody>
            {items.map((zone) => (
              <TR key={zone._id}>
                <TDPrimary>
                  {zone.name}
                  <TDMeta>
                    <span className="font-mono">{zone.zone_code}</span>
                  </TDMeta>
                </TDPrimary>
                <TD>
                  {zone.city}
                  <TDMeta>{zone.state}</TDMeta>
                </TD>
                <TD numeric>{zone.population_covered.toLocaleString("en-IN")}</TD>
                <TD>
                  <Badge tone={zone.is_active ? "stable" : "neutral"}>
                    {zone.is_active ? "Active" : "Inactive"}
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
