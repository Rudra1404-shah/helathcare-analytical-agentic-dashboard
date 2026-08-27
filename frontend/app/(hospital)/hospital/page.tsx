import { AlertTriangle, Bed, PackageCheck } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { CapacityCards } from "@/components/data/capacity-cards";
import { TriageBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { PageHeader, Panel, PanelHeader } from "@/components/ui/panel";
import {
  CardsSkeleton,
  EmptyState,
  ErrorState,
  TableSkeleton,
} from "@/components/ui/states";
import { Table, TBody, TD, TDMeta, TDPrimary, TH, THead, TR, TableWrap } from "@/components/ui/table";
import { apiTry } from "@/lib/api";
import { humanise, quantity, stayDuration } from "@/lib/format";
import { requireSession, resolveHospital } from "@/lib/session";
import type {
  CapacityCard,
  LowStockAlert,
  Paginated,
  PatientCase,
} from "@/lib/types";

export const metadata: Metadata = { title: "Live overview" };

export default async function HospitalOverviewPage() {
  const user = await requireSession();
  const { hospital, error } = await resolveHospital(user);

  if (!hospital) {
    return (
      <>
        <PageHeader title="Live overview" />
        <Panel>
          {error ? (
            <ErrorState message={error} />
          ) : (
            <EmptyState
              icon={Bed}
              title="No hospital is linked to this account"
              description="A hospital account is scoped to the hospital that issued it. Ask the Health Ministry to register the hospital before using the operational modules."
            />
          )}
        </Panel>
      </>
    );
  }

  return (
    <>
      <PageHeader
        title="Live overview"
        description={`Current capacity and open cases at ${hospital.name}. Bed counts move as cases are admitted and discharged, so this is what is genuinely free right now.`}
      />

      <Suspense fallback={<CardsSkeleton />}>
        <CapacityRow hospitalId={hospital._id} />
      </Suspense>

      <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <Panel>
          <Suspense
            fallback={
              <>
                <PanelHeader title="Open cases" description="Loading" />
                <TableSkeleton rows={6} columns={4} />
              </>
            }
          >
            <OpenCases hospitalId={hospital._id} />
          </Suspense>
        </Panel>

        <Panel className="h-fit">
          <Suspense
            fallback={
              <>
                <PanelHeader title="Stock alerts" description="Loading" />
                <TableSkeleton rows={4} columns={2} />
              </>
            }
          >
            <StockAlerts hospitalId={hospital._id} />
          </Suspense>
        </Panel>
      </div>
    </>
  );
}

async function CapacityRow({ hospitalId }: { hospitalId: string }) {
  const result = await apiTry<CapacityCard[]>(
    `/hospitals/${hospitalId}/inventory/capacity`,
  );

  if (!result.ok) {
    return (
      <Panel>
        <ErrorState message={result.error} />
      </Panel>
    );
  }

  return <CapacityCards cards={result.data} />;
}

async function OpenCases({ hospitalId }: { hospitalId: string }) {
  const result = await apiTry<Paginated<PatientCase>>(`/hospitals/${hospitalId}/cases`, {
    query: { open_only: true, limit: 10 },
  });

  if (!result.ok) {
    return (
      <>
        <PanelHeader title="Open cases" />
        <ErrorState message={result.error} />
      </>
    );
  }

  const { items, meta } = result.data;

  if (items.length === 0) {
    return (
      <>
        <PanelHeader title="Open cases" />
        <EmptyState
          title="No open cases"
          description="Every case at this hospital has been closed. New admissions appear here as soon as they are opened."
          action={
            <Button asChild size="sm">
              <Link href="/hospital/cases">Go to cases</Link>
            </Button>
          }
        />
      </>
    );
  }

  return (
    <>
      <PanelHeader
        title="Open cases"
        description={`${meta.total} currently occupying capacity`}
        action={
          <Button asChild variant="secondary" size="sm">
            <Link href="/hospital/cases">Triage board</Link>
          </Button>
        }
      />
      <TableWrap>
        <Table className="min-w-[34rem]">
          <THead>
            <tr>
              <TH>Case</TH>
              <TH>Triage</TH>
              <TH>Bed</TH>
              <TH numeric>Length of stay</TH>
            </tr>
          </THead>
          <TBody>
            {items.map((item) => (
              <TR key={item._id}>
                <TDPrimary>
                  <span className="font-mono text-xs">{item.case_number}</span>
                  <TDMeta>{item.chief_symptoms.slice(0, 2).join(", ")}</TDMeta>
                </TDPrimary>
                <TD>
                  <TriageBadge level={item.triage_level} />
                </TD>
                <TD>
                  {item.bed_allocated ?? "Unassigned"}
                  <TDMeta>{humanise(item.status)}</TDMeta>
                </TD>
                <TD numeric>{stayDuration(item.admitted_at, item.discharged_at)}</TD>
              </TR>
            ))}
          </TBody>
        </Table>
      </TableWrap>
    </>
  );
}

async function StockAlerts({ hospitalId }: { hospitalId: string }) {
  const result = await apiTry<LowStockAlert[]>("/inventory/alerts", {
    query: { hospital_id: hospitalId },
  });

  if (!result.ok) {
    return (
      <>
        <PanelHeader title="Stock alerts" />
        <ErrorState message={result.error} />
      </>
    );
  }

  if (result.data.length === 0) {
    return (
      <>
        <PanelHeader title="Stock alerts" />
        <EmptyState
          icon={PackageCheck}
          title="Everything is above threshold"
          description="No tracked resource has reached its safety level."
        />
      </>
    );
  }

  return (
    <>
      <PanelHeader
        title="Stock alerts"
        description={`${result.data.length} at or below the safety threshold`}
        action={
          <Button asChild variant="secondary" size="sm">
            <Link href="/hospital/inventory?below_threshold=true">Restock</Link>
          </Button>
        }
      />
      <ul className="divide-y divide-border">
        {result.data.map((alert) => (
          <li
            key={alert.item_id}
            className="flex items-start justify-between gap-3 px-4 py-3"
          >
            <div className="min-w-0">
              <p className="flex items-center gap-1.5 text-sm font-medium text-foreground">
                <AlertTriangle
                  className="size-3.5 shrink-0 text-critical"
                  strokeWidth={1.75}
                  aria-hidden="true"
                />
                <span className="truncate">{alert.item_name}</span>
              </p>
              <p className="mt-0.5 text-xs text-muted-foreground">
                {humanise(alert.category)}
              </p>
            </div>
            <p className="shrink-0 text-right">
              <span className="font-mono text-sm font-medium tabular-nums text-critical">
                {quantity(alert.available_stock)}
              </span>
              <span className="block text-xs text-muted-foreground">
                of {quantity(alert.min_safety_threshold, alert.unit)} safe
              </span>
            </p>
          </li>
        ))}
      </ul>
    </>
  );
}
