import {
  Activity,
  AlertTriangle,
  Bed,
  HeartPulse,
  Package,
  Siren,
  Stethoscope,
  TrendingUp,
} from "lucide-react";
import type { Metadata } from "next";
import { Suspense } from "react";

import { AlertList } from "@/components/data/alert-list";
import {
  ConfidenceBadge,
  MetricBar,
  StatTile,
  TrendIndicator,
  daysText,
} from "@/components/data/analytics-primitives";
import { ForecastChart } from "@/components/data/forecast-chart";
import { Badge } from "@/components/ui/badge";
import { PageHeader, Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import { CardsSkeleton, EmptyState, ErrorState, TableSkeleton } from "@/components/ui/states";
import { Table, TBody, TD, TDMeta, TDPrimary, TH, THead, TR, TableWrap } from "@/components/ui/table";
import { apiTry } from "@/lib/api";
import { dateOnly, humanise, quantity } from "@/lib/format";
import { withHospital } from "@/lib/hospital-page";
import type {
  RealtimeMonitoring,
  ResourcePrediction,
  SmartAlerts,
  SurgeForecast,
  WorkforceReallocation,
} from "@/lib/types";

export const metadata: Metadata = { title: "AI Intelligence Hub" };

/**
 * Operational intelligence for one hospital.
 *
 * Unlike the ministry view this is a single scrolling board rather than tabs:
 * a charge nurse needs occupancy, who is overloaded, and what is running out
 * visible at once, not one at a time behind a click. Each region streams in its
 * own Suspense boundary so a slow module never blanks the others.
 */
export default async function HospitalAnalyticsPage() {
  return withHospital("AI Intelligence Hub", (hospital) => (
    <>
      <PageHeader
        title="AI Intelligence Hub"
        description={`Live occupancy, workload strain, and resource countdown for ${hospital.name}. Figures inferred rather than measured are labelled as such.`}
      />

      <Suspense fallback={<CardsSkeleton count={4} />}>
        <Gauges hospitalId={hospital._id} />
      </Suspense>

      <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <div className="grid gap-4">
          <Panel>
            <Suspense
              fallback={
                <>
                  <PanelHeader title="Doctor workload" description="Loading" />
                  <TableSkeleton rows={5} columns={3} />
                </>
              }
            >
              <Burnout hospitalId={hospital._id} />
            </Suspense>
          </Panel>

          <Panel>
            <Suspense
              fallback={
                <>
                  <PanelHeader title="Stockout countdown" description="Loading" />
                  <TableSkeleton rows={5} columns={5} />
                </>
              }
            >
              <Stockouts hospitalId={hospital._id} />
            </Suspense>
          </Panel>

          <Panel>
            <Suspense
              fallback={
                <>
                  <PanelHeader title="Admissions forecast" description="Loading" />
                  <TableSkeleton rows={4} columns={3} />
                </>
              }
            >
              <Forecast hospitalId={hospital._id} />
            </Suspense>
          </Panel>
        </div>

        <Panel className="h-fit">
          <Suspense
            fallback={
              <>
                <PanelHeader title="Smart alerts" description="Loading" />
                <TableSkeleton rows={5} columns={2} />
              </>
            }
          >
            <Alerts hospitalId={hospital._id} />
          </Suspense>
        </Panel>
      </div>
    </>
  ));
}

// --------------------------------------------------------------------------
// Bed and ICU gauges
// --------------------------------------------------------------------------
async function Gauges({ hospitalId }: { hospitalId: string }) {
  const result = await apiTry<RealtimeMonitoring>(
    `/hospitals/${hospitalId}/analytics/realtime`,
  );

  if (!result.ok) {
    return (
      <Panel>
        <ErrorState message={result.error} />
      </Panel>
    );
  }

  const data = result.data;
  const urgent = data.triage_breakdown
    .filter((entry) => entry.triage_level <= 2)
    .reduce((sum, entry) => sum + entry.open_cases, 0);

  return (
    <>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatTile
          label="Open cases"
          value={data.open_cases}
          meta={`${data.admitted_cases} admitted, ${data.observation_cases} under observation`}
          icon={Bed}
        />
        <StatTile
          label="In ICU"
          value={data.icu_cases}
          meta={`of ${data.icu_beds} ICU beds`}
          icon={HeartPulse}
          tone={
            data.icu_occupancy_ratio !== null && data.icu_occupancy_ratio >= 0.9
              ? "critical"
              : "default"
          }
        />
        <StatTile
          label="Urgent triage"
          value={urgent}
          meta="Immediate and urgent cases currently open"
          icon={Activity}
          tone={urgent > 0 ? "warning" : "default"}
        />
        <StatTile
          label="Awaiting triage"
          value={data.unclassified_cases}
          meta="Open cases with no triage level or case type"
          icon={AlertTriangle}
        />
      </div>

      <Panel className="mt-4">
        <PanelHeader
          title="Capacity gauges"
          description="Occupancy against sanctioned capacity and tracked stock"
        />
        <div className="grid divide-y divide-border sm:grid-cols-2 sm:divide-y-0">
          <MetricBar
            label="General beds"
            meta={`${data.open_cases} open of ${data.total_sanctioned_beds} sanctioned`}
            ratio={data.bed_occupancy_ratio}
          />
          <MetricBar
            label="ICU"
            meta={`${data.icu_cases} of ${data.icu_beds} ICU beds`}
            ratio={data.icu_occupancy_ratio}
          />
          <MetricBar
            label="Ventilators in use"
            meta="Share of tracked ventilator stock allocated"
            ratio={data.ventilator_utilisation_ratio}
          />
          <MetricBar
            label="Oxygen in use"
            meta="Share of tracked oxygen stock allocated"
            ratio={data.oxygen_utilisation_ratio}
          />
        </div>
      </Panel>
    </>
  );
}

// --------------------------------------------------------------------------
// Doctor burnout
// --------------------------------------------------------------------------
async function Burnout({ hospitalId }: { hospitalId: string }) {
  const result = await apiTry<WorkforceReallocation>(
    `/hospitals/${hospitalId}/analytics/workforce`,
  );

  if (!result.ok) {
    return (
      <>
        <PanelHeader title="Doctor workload" />
        <ErrorState message={result.error} />
      </>
    );
  }

  const data = result.data;

  if (!data.has_capacity_data) {
    return (
      <>
        <PanelHeader title="Doctor workload" />
        <EmptyState
          icon={Stethoscope}
          title="No doctors onboarded"
          description="The burnout index compares each doctor's open caseload against the daily ceiling set at onboarding. Onboard a doctor to see it here."
        />
      </>
    );
  }

  const ranked = [...data.doctors].sort(
    (left, right) => (right.burnout_index ?? 0) - (left.burnout_index ?? 0),
  );

  return (
    <>
      <PanelHeader
        title="Doctor workload"
        description={`${data.overloaded_doctor_count} of ${data.doctor_count} at or over their daily ceiling`}
        action={
          data.mean_burnout_index === null ? undefined : (
            <Badge tone={data.mean_burnout_index >= 1 ? "warning" : "neutral"}>
              Mean {data.mean_burnout_index.toFixed(2)}
            </Badge>
          )
        }
      />
      <div className="divide-y divide-border">
        {ranked.map((doctor) => (
          <MetricBar
            key={doctor.doctor_id}
            label={doctor.full_name}
            meta={`${doctor.specialization} · ${doctor.active_load} open of ${doctor.max_daily_patients} daily${doctor.is_available ? "" : " · unavailable"}`}
            ratio={doctor.burnout_index}
          />
        ))}
      </div>

      {data.suggestions.length > 0 ? (
        <div className="border-t border-border bg-surface-muted px-4 py-3">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Suggested reallocation
          </h3>
          <ul className="mt-2 space-y-1.5">
            {data.suggestions.map((suggestion) => (
              <li
                key={`${suggestion.from_department_id}-${suggestion.to_department_id}`}
                className="text-sm text-foreground"
              >
                Move cover from{" "}
                <span className="font-mono text-xs">
                  {suggestion.from_department_id.slice(-8)}
                </span>{" "}
                to{" "}
                <span className="font-mono text-xs">
                  {suggestion.to_department_id.slice(-8)}
                </span>
                <span className="block text-xs text-muted-foreground">
                  {suggestion.reason}
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </>
  );
}

// --------------------------------------------------------------------------
// Stockout countdown
// --------------------------------------------------------------------------
async function Stockouts({ hospitalId }: { hospitalId: string }) {
  const result = await apiTry<ResourcePrediction>(
    `/hospitals/${hospitalId}/analytics/resources`,
  );

  if (!result.ok) {
    return (
      <>
        <PanelHeader title="Stockout countdown" />
        <ErrorState message={result.error} />
      </>
    );
  }

  const data = result.data;

  if (data.projections.length === 0) {
    return (
      <>
        <PanelHeader title="Stockout countdown" />
        <EmptyState
          icon={Package}
          title="No stock lines are tracked"
          description="Add inventory lines to project how many days of each resource remain at the current rate of demand."
        />
      </>
    );
  }

  const ordered = [...data.projections].sort(
    (left, right) => (left.days_to_stockout ?? Infinity) - (right.days_to_stockout ?? Infinity),
  );

  return (
    <>
      <PanelHeader
        title="Stockout countdown"
        description={`${data.at_risk_count} categories projected to run out within 14 days`}
        action={<Badge tone="info">Estimated from {data.window_days}-day demand</Badge>}
      />
      <TableWrap>
        <Table className="min-w-[38rem]">
          <THead>
            <tr>
              <TH>Category</TH>
              <TH numeric>Available</TH>
              <TH numeric>Est. burn / day</TH>
              <TH numeric>Days left</TH>
              <TH>Projected stockout</TH>
            </tr>
          </THead>
          <TBody>
            {ordered.map((projection) => (
              <TR key={projection.category}>
                <TDPrimary>
                  {humanise(projection.category)}
                  {projection.is_below_threshold ? (
                    <TDMeta>
                      <span className="text-critical">Below safety threshold</span>
                    </TDMeta>
                  ) : (
                    <TDMeta>
                      Safe level {quantity(projection.min_safety_threshold)}
                    </TDMeta>
                  )}
                </TDPrimary>
                <TD numeric>{quantity(projection.available_stock, projection.unit)}</TD>
                <TD numeric>{projection.daily_burn_rate.toFixed(1)}</TD>
                <TD numeric>
                  <span
                    className={
                      projection.days_to_stockout !== null &&
                      projection.days_to_stockout <= 7
                        ? "text-critical"
                        : undefined
                    }
                  >
                    {daysText(projection.days_to_stockout)}
                  </span>
                </TD>
                <TD>
                  {projection.projected_stockout_on
                    ? dateOnly(projection.projected_stockout_on)
                    : "No demand observed"}
                </TD>
              </TR>
            ))}
          </TBody>
        </Table>
      </TableWrap>
    </>
  );
}

// --------------------------------------------------------------------------
// Admissions forecast
// --------------------------------------------------------------------------
async function Forecast({ hospitalId }: { hospitalId: string }) {
  const result = await apiTry<SurgeForecast>(`/hospitals/${hospitalId}/analytics/surge`);

  if (!result.ok) {
    return (
      <>
        <PanelHeader title="Admissions forecast" />
        <ErrorState message={result.error} />
      </>
    );
  }

  const data = result.data;

  return (
    <>
      <PanelHeader
        title="Admissions forecast"
        description={`${data.horizon_days} days ahead, fitted on ${data.history_window_days} days of history`}
        action={<ConfidenceBadge confidence={data.confidence} />}
      />
      <PanelBody>
        {data.confidence === "INSUFFICIENT_DATA" ? (
          <EmptyState
            icon={TrendingUp}
            title="Not enough history to project"
            description="A trend needs at least a week of days with admissions on them. Rather than draw a guess, no line is shown until there is enough to fit."
          />
        ) : (
          <>
            <div className="flex flex-wrap items-center justify-between gap-3 pb-3">
              <TrendIndicator
                direction={data.trend_direction}
                perDay={data.trend_per_day}
              />
              <p className="text-sm text-muted-foreground">
                <span className="font-mono font-medium tabular-nums text-foreground">
                  {Math.round(data.projected_7_day_total)}
                </span>{" "}
                projected over 7 days ·{" "}
                <span className="font-mono font-medium tabular-nums text-foreground">
                  {Math.round(data.projected_14_day_total)}
                </span>{" "}
                over 14
              </p>
            </div>
            <ForecastChart
              history={data.history}
              points={data.points}
              historyWindowDays={data.history_window_days}
            />
          </>
        )}
      </PanelBody>
    </>
  );
}

// --------------------------------------------------------------------------
// Smart alerts
// --------------------------------------------------------------------------
async function Alerts({ hospitalId }: { hospitalId: string }) {
  const result = await apiTry<SmartAlerts>(`/hospitals/${hospitalId}/analytics/alerts`);

  if (!result.ok) {
    return (
      <>
        <PanelHeader title="Smart alerts" />
        <ErrorState message={result.error} />
      </>
    );
  }

  const data = result.data;

  return (
    <>
      <PanelHeader
        title="Smart alerts"
        description={
          data.alerts.length === 0
            ? "Nothing above threshold"
            : `${data.critical_count} critical, ${data.high_count} high, ${data.medium_count} medium`
        }
        action={
          data.critical_count > 0 ? (
            <Siren className="size-4 text-critical" strokeWidth={1.75} aria-hidden="true" />
          ) : undefined
        }
      />
      <AlertList alerts={data.alerts} />
    </>
  );
}
