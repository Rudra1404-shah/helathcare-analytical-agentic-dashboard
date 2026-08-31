import {
  Activity,
  AlertTriangle,
  Bed,
  Building2,
  Gavel,
  HeartPulse,
  Package,
  Scale,
  Siren,
  Stethoscope,
  TrendingUp,
  Users,
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
  ratioText,
} from "@/components/data/analytics-primitives";
import { ForecastChart } from "@/components/data/forecast-chart";
import { Badge } from "@/components/ui/badge";
import { PageHeader, Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import {
  CardsSkeleton,
  EmptyState,
  ErrorState,
  TableSkeleton,
} from "@/components/ui/states";
import { Table, TBody, TD, TDMeta, TDPrimary, TH, THead, TR, TableWrap } from "@/components/ui/table";
import { TabNav, type TabItem } from "@/components/ui/tab-nav";
import { apiTry } from "@/lib/api";
import { dateOnly, humanise, quantity } from "@/lib/format";
import type {
  NationalOverview,
  OutbreakDetection,
  PolicyImpact,
  RealtimeMonitoring,
  ResourcePrediction,
  SmartAlerts,
  SurgeForecast,
  WorkforceReallocation,
} from "@/lib/types";

export const metadata: Metadata = { title: "AI Intelligence Hub" };

const MODULES: TabItem[] = [
  { key: "realtime", label: "Real-time monitoring" },
  { key: "outbreaks", label: "Outbreak detection" },
  { key: "surge", label: "Surge forecast" },
  { key: "workforce", label: "Workforce" },
  { key: "resources", label: "Resources" },
  { key: "alerts", label: "Smart alerts" },
  { key: "policy-impact", label: "Policy impact" },
];

const DEFAULT_MODULE = "alerts";

/**
 * The ministry's command centre.
 *
 * Modules are selected through the URL rather than client tab state, so only
 * the module on screen fetches and each view is a link an official can send to
 * a colleague. The summary strip is always present because it is what the room
 * looks at; everything below it streams in its own Suspense boundary so one
 * slow module never blanks the page.
 */
export default async function GovernmentAnalyticsPage({
  searchParams,
}: {
  searchParams: Promise<{ module?: string }>;
}) {
  const params = await searchParams;
  const active = MODULES.some((item) => item.key === params.module)
    ? (params.module as string)
    : DEFAULT_MODULE;

  return (
    <>
      <PageHeader
        title="AI Intelligence Hub"
        description="Seven analytical modules reading across every registered hospital. Figures derived rather than measured say so, and a module without enough history says that too rather than guessing."
      />

      <Suspense fallback={<CardsSkeleton count={4} />}>
        <SummaryStrip />
      </Suspense>

      <div className="mt-6">
        <TabNav items={MODULES} active={active} basePath="/gov/analytics" />
      </div>

      <div className="mt-4">
        <Suspense key={active} fallback={<ModuleSkeleton />}>
          <ActiveModule module={active} />
        </Suspense>
      </div>
    </>
  );
}

function ModuleSkeleton() {
  return (
    <Panel>
      <PanelHeader title="Loading" description="Reading the national picture" />
      <TableSkeleton rows={6} columns={4} />
    </Panel>
  );
}

async function ActiveModule({ module }: { module: string }) {
  switch (module) {
    case "realtime":
      return <RealtimePanel />;
    case "outbreaks":
      return <OutbreakPanel />;
    case "surge":
      return <SurgePanel />;
    case "workforce":
      return <WorkforcePanel />;
    case "resources":
      return <ResourcePanel />;
    case "policy-impact":
      return <PolicyPanel />;
    default:
      return <AlertsPanel />;
  }
}

// --------------------------------------------------------------------------
// Summary strip
// --------------------------------------------------------------------------
async function SummaryStrip() {
  const result = await apiTry<NationalOverview>("/analytics/national/overview");

  if (!result.ok) {
    return (
      <Panel>
        <ErrorState message={result.error} />
      </Panel>
    );
  }

  const data = result.data;

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <StatTile
        label="Hospitals reporting"
        value={data.hospital_count}
        meta={`${data.zone_count} zones, ${data.population_covered.toLocaleString("en-IN")} residents covered`}
        icon={Building2}
      />
      <StatTile
        label="Bed occupancy"
        value={ratioText(data.bed_occupancy_ratio)}
        meta={`${data.open_cases.toLocaleString("en-IN")} open cases against ${data.total_sanctioned_beds.toLocaleString("en-IN")} sanctioned beds`}
        icon={Bed}
        tone={toneForOccupancy(data.bed_occupancy_ratio)}
      />
      <StatTile
        label="Critical alerts"
        value={data.critical_alert_count}
        meta={`${data.high_alert_count} further alerts at high severity`}
        icon={Siren}
        tone={data.critical_alert_count > 0 ? "critical" : "default"}
      />
      <StatTile
        label="Outbreak signals"
        value={data.outbreak_signal_count}
        meta={`${data.at_risk_resource_count} resource lines nearing stockout`}
        icon={Activity}
        tone={data.outbreak_signal_count > 0 ? "warning" : "default"}
      />
    </div>
  );
}

function toneForOccupancy(ratio: number | null): "default" | "warning" | "critical" {
  if (ratio === null) return "default";
  if (ratio >= 0.9) return "critical";
  if (ratio >= 0.75) return "warning";
  return "default";
}

// --------------------------------------------------------------------------
// Module 1 -- Real-time monitoring
// --------------------------------------------------------------------------
async function RealtimePanel() {
  const result = await apiTry<RealtimeMonitoring>("/analytics/national/realtime");

  if (!result.ok) {
    return (
      <Panel>
        <PanelHeader title="Real-time monitoring" />
        <ErrorState message={result.error} />
      </Panel>
    );
  }

  const data = result.data;

  if (data.hospital_count === 0) {
    return (
      <Panel>
        <PanelHeader title="Real-time monitoring" />
        <EmptyState
          icon={Building2}
          title="No hospitals are reporting yet"
          description="Occupancy appears here once a hospital has been registered and accredited on the directory."
        />
      </Panel>
    );
  }

  const triaged = data.triage_breakdown.reduce((sum, entry) => sum + entry.open_cases, 0);

  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
      <Panel>
        <PanelHeader
          title="Live occupancy"
          description={`Across ${data.hospital_count} hospitals`}
        />
        <div className="divide-y divide-border">
          <MetricBar
            label="General beds"
            meta={`${data.open_cases} open cases of ${data.total_sanctioned_beds} sanctioned`}
            ratio={data.bed_occupancy_ratio}
          />
          <MetricBar
            label="ICU"
            meta={`${data.icu_cases} critical cases of ${data.icu_beds} ICU beds`}
            ratio={data.icu_occupancy_ratio}
          />
          <MetricBar
            label="Ventilators in use"
            meta="Share of tracked ventilator stock currently allocated"
            ratio={data.ventilator_utilisation_ratio}
          />
          <MetricBar
            label="Oxygen in use"
            meta="Share of tracked oxygen stock currently allocated"
            ratio={data.oxygen_utilisation_ratio}
          />
        </div>
      </Panel>

      <Panel>
        <PanelHeader
          title="Triage mix"
          description={`${triaged} triaged, ${data.unclassified_cases} awaiting classification`}
        />
        {triaged === 0 && data.unclassified_cases === 0 ? (
          <EmptyState
            icon={HeartPulse}
            title="No open cases"
            description="Every case on the platform has been closed. Triage counts appear here as soon as somebody is admitted."
          />
        ) : (
          <div className="divide-y divide-border">
            {data.triage_breakdown.map((entry) => (
              <MetricBar
                key={entry.triage_level}
                label={TRIAGE_LABELS[entry.triage_level]}
                meta={`Level ${entry.triage_level}`}
                ratio={triaged === 0 ? null : entry.open_cases / triaged}
                valueLabel={String(entry.open_cases)}
                tone={entry.triage_level <= 2 ? "critical" : "default"}
              />
            ))}
          </div>
        )}
      </Panel>
    </div>
  );
}

const TRIAGE_LABELS: Record<number, string> = {
  1: "Immediate",
  2: "Urgent",
  3: "Standard",
  4: "Non-urgent",
};

// --------------------------------------------------------------------------
// Module 2 -- Outbreak detection
// --------------------------------------------------------------------------
async function OutbreakPanel() {
  const result = await apiTry<OutbreakDetection>("/analytics/national/outbreaks");

  if (!result.ok) {
    return (
      <Panel>
        <PanelHeader title="Outbreak detection" />
        <ErrorState message={result.error} />
      </Panel>
    );
  }

  const data = result.data;

  if (data.evaluated_count === 0) {
    return (
      <Panel>
        <PanelHeader title="Outbreak detection" />
        <EmptyState
          icon={Activity}
          title="No notifiable cases to analyse"
          description="Clustering is tested only on case types marked notifiable, within zones that record a population. Signals appear here once notifiable cases are recorded against a registered zone."
        />
      </Panel>
    );
  }

  return (
    <Panel>
      <PanelHeader
        title="Outbreak detection"
        description={`${data.anomaly_count} of ${data.evaluated_count} zone-and-disease pairs above a z-score of ${data.threshold} over ${data.window_days} days`}
      />
      <TableWrap>
        <Table className="min-w-[52rem]">
          <THead>
            <tr>
              <TH>Zone</TH>
              <TH>Condition</TH>
              <TH numeric>Cases today</TH>
              <TH numeric>Per 100k</TH>
              <TH numeric>Baseline</TH>
              <TH numeric>Z-score</TH>
              <TH>Assessment</TH>
            </tr>
          </THead>
          <TBody>
            {data.signals.map((signal) => (
              <TR key={`${signal.zone_code}-${signal.case_type_id}`}>
                <TDPrimary>
                  {signal.zone_name}
                  <TDMeta>
                    <span className="font-mono">{signal.zone_code}</span> · {signal.city}
                  </TDMeta>
                </TDPrimary>
                <TD>
                  {signal.case_type_name}
                  <TDMeta>
                    <span className="font-mono">{signal.icd10_code}</span>
                  </TDMeta>
                </TD>
                <TD numeric>{signal.observed_cases}</TD>
                <TD numeric>{rate(signal.observed_rate_per_100k)}</TD>
                <TD numeric>{rate(signal.baseline_mean_rate_per_100k)}</TD>
                <TD numeric>
                  {signal.z_score === null ? "—" : signal.z_score.toFixed(2)}
                </TD>
                <TD>
                  <div className="flex flex-wrap items-center gap-1.5">
                    {signal.is_anomaly ? (
                      <Badge tone="critical">Anomaly</Badge>
                    ) : (
                      <Badge tone="stable">Within baseline</Badge>
                    )}
                    <ConfidenceBadge confidence={signal.confidence} />
                  </div>
                </TD>
              </TR>
            ))}
          </TBody>
        </Table>
      </TableWrap>
    </Panel>
  );
}

function rate(value: number | null): string {
  return value === null ? "—" : value.toFixed(2);
}

// --------------------------------------------------------------------------
// Module 3 -- Surge forecast
// --------------------------------------------------------------------------
async function SurgePanel() {
  const result = await apiTry<SurgeForecast>("/analytics/national/surge");

  if (!result.ok) {
    return (
      <Panel>
        <PanelHeader title="Surge forecast" />
        <ErrorState message={result.error} />
      </Panel>
    );
  }

  const data = result.data;

  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
      <Panel>
        <PanelHeader
          title="Admissions projection"
          description={`${data.horizon_days} days ahead, fitted on ${data.history_window_days} days of history`}
          action={<ConfidenceBadge confidence={data.confidence} />}
        />
        <PanelBody>
          {data.confidence === "INSUFFICIENT_DATA" ? (
            <EmptyState
              icon={TrendingUp}
              title="Not enough history to project"
              description="A trend needs at least a week of days with admissions on them. The projection appears here once enough has accumulated; until then no line is drawn rather than a guess."
            />
          ) : (
            <ForecastChart
              history={data.history}
              points={data.points}
              historyWindowDays={data.history_window_days}
            />
          )}
        </PanelBody>
      </Panel>

      <Panel className="h-fit">
        <PanelHeader title="Projected load" />
        <div className="divide-y divide-border">
          <div className="px-4 py-3">
            <p className="text-sm text-muted-foreground">Trend</p>
            <p className="mt-1">
              <TrendIndicator
                direction={data.trend_direction}
                perDay={data.trend_per_day}
              />
            </p>
          </div>
          <div className="px-4 py-3">
            <p className="text-sm text-muted-foreground">Next 7 days</p>
            <p className="mt-1 font-mono text-2xl font-semibold tabular-nums text-foreground">
              {Math.round(data.projected_7_day_total)}
            </p>
            <p className="mt-0.5 text-xs text-muted-foreground">projected admissions</p>
          </div>
          <div className="px-4 py-3">
            <p className="text-sm text-muted-foreground">Next 14 days</p>
            <p className="mt-1 font-mono text-2xl font-semibold tabular-nums text-foreground">
              {Math.round(data.projected_14_day_total)}
            </p>
            <p className="mt-0.5 text-xs text-muted-foreground">projected admissions</p>
          </div>
        </div>
      </Panel>
    </div>
  );
}

// --------------------------------------------------------------------------
// Module 4 -- Workforce
// --------------------------------------------------------------------------
async function WorkforcePanel() {
  const result = await apiTry<WorkforceReallocation>("/analytics/national/workforce");

  if (!result.ok) {
    return (
      <Panel>
        <PanelHeader title="Workforce" />
        <ErrorState message={result.error} />
      </Panel>
    );
  }

  const data = result.data;

  if (!data.has_capacity_data) {
    return (
      <Panel>
        <PanelHeader title="Workforce" />
        <EmptyState
          icon={Stethoscope}
          title="No doctors on file"
          description="Workload strain is measured against each doctor's declared daily ceiling. Onboard doctors to see where the pressure sits."
        />
      </Panel>
    );
  }

  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
      <Panel>
        <PanelHeader
          title="Departmental strain"
          description="Aggregated nationally. Individual doctors are named only on their own hospital's view."
        />
        <div className="divide-y divide-border">
          {data.departments.slice(0, 12).map((department) => (
            <MetricBar
              key={department.department_id}
              label={
                <span className="font-mono text-xs">
                  {department.department_id.slice(-8)}
                </span>
              }
              meta={`${department.doctor_count} doctors · ${department.active_load} open cases of ${department.daily_capacity} daily capacity`}
              ratio={department.burnout_index}
            />
          ))}
        </div>
      </Panel>

      <div className="grid gap-4">
        <div className="grid grid-cols-2 gap-4">
          <StatTile
            label="Doctors over ceiling"
            value={data.overloaded_doctor_count}
            meta={`of ${data.doctor_count} on file`}
            icon={Users}
            tone={data.overloaded_doctor_count > 0 ? "critical" : "default"}
          />
          <StatTile
            label="Mean burnout index"
            value={
              data.mean_burnout_index === null
                ? "—"
                : data.mean_burnout_index.toFixed(2)
            }
            meta={`${data.total_active_load} open cases against ${data.total_daily_capacity} daily capacity`}
            icon={Activity}
          />
        </div>

        <Panel>
          <PanelHeader title="Shift cover" />
          <TableWrap>
            <Table className="min-w-0">
              <THead>
                <tr>
                  <TH>Shift</TH>
                  <TH numeric>Doctors</TH>
                  <TH numeric>Medical</TH>
                  <TH numeric>Support</TH>
                </tr>
              </THead>
              <TBody>
                {data.shift_balance.map((entry) => (
                  <TR key={entry.shift}>
                    <TDPrimary>{humanise(entry.shift)}</TDPrimary>
                    <TD numeric>{entry.doctor_count}</TD>
                    <TD numeric>{entry.medical_staff_count}</TD>
                    <TD numeric>{entry.support_staff_count}</TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          </TableWrap>
        </Panel>
      </div>
    </div>
  );
}

// --------------------------------------------------------------------------
// Module 5 -- Resources
// --------------------------------------------------------------------------
async function ResourcePanel() {
  const result = await apiTry<ResourcePrediction>("/analytics/national/resources");

  if (!result.ok) {
    return (
      <Panel>
        <PanelHeader title="Resource prediction" />
        <ErrorState message={result.error} />
      </Panel>
    );
  }

  const data = result.data;

  if (data.projections.length === 0) {
    return (
      <Panel>
        <PanelHeader title="Resource prediction" />
        <EmptyState
          icon={Package}
          title="No stock lines are tracked"
          description="Days-to-stockout is projected from tracked inventory against observed case demand. Register stock lines to see the countdown here."
        />
      </Panel>
    );
  }

  const ordered = [...data.projections].sort(
    (left, right) => (left.days_to_stockout ?? Infinity) - (right.days_to_stockout ?? Infinity),
  );

  return (
    <Panel>
      <PanelHeader
        title="Resource prediction"
        description={`${data.at_risk_count} lines projected to run out within 14 days`}
        action={<EstimateNote windowDays={data.window_days} />}
      />
      <TableWrap>
        <Table className="min-w-[48rem]">
          <THead>
            <tr>
              <TH>Category</TH>
              <TH numeric>Available</TH>
              <TH numeric>Safety level</TH>
              <TH numeric>Est. burn / day</TH>
              <TH numeric>Days left</TH>
              <TH>Projected stockout</TH>
            </tr>
          </THead>
          <TBody>
            {ordered.slice(0, 40).map((projection) => (
              <TR key={`${projection.hospital_id}-${projection.category}`}>
                <TDPrimary>
                  {humanise(projection.category)}
                  <TDMeta>
                    {projection.line_count} line{projection.line_count === 1 ? "" : "s"}
                  </TDMeta>
                </TDPrimary>
                <TD numeric>{quantity(projection.available_stock, projection.unit)}</TD>
                <TD numeric>{quantity(projection.min_safety_threshold)}</TD>
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
    </Panel>
  );
}

/**
 * The platform holds no stock-movement ledger, so a burn rate is inferred from
 * case demand. Saying so on the panel is the difference between an estimate and
 * a claim.
 */
function EstimateNote({ windowDays }: { windowDays: number }) {
  return (
    <Badge tone="info">Estimated from {windowDays}-day case demand</Badge>
  );
}

// --------------------------------------------------------------------------
// Module 6 -- Smart alerts
// --------------------------------------------------------------------------
async function AlertsPanel() {
  const result = await apiTry<SmartAlerts>("/analytics/national/alerts");

  if (!result.ok) {
    return (
      <Panel>
        <PanelHeader title="Smart alerts" />
        <ErrorState message={result.error} />
      </Panel>
    );
  }

  const data = result.data;

  return (
    <div className="grid gap-4">
      <div className="grid grid-cols-2 gap-4 xl:grid-cols-4">
        <StatTile
          label="Critical"
          value={data.critical_count}
          meta="Act now"
          icon={Siren}
          tone={data.critical_count > 0 ? "critical" : "default"}
        />
        <StatTile
          label="High"
          value={data.high_count}
          meta="Act today"
          icon={AlertTriangle}
          tone={data.high_count > 0 ? "warning" : "default"}
        />
        <StatTile label="Medium" value={data.medium_count} meta="Act this week" />
        <StatTile label="Info" value={data.info_count} meta="Worth knowing" />
      </div>

      <Panel>
        <PanelHeader
          title="Action list"
          description="Synthesised from occupancy, outbreak, workforce, and resource signals, most severe first"
        />
        <AlertList alerts={data.alerts} />
      </Panel>
    </div>
  );
}

// --------------------------------------------------------------------------
// Module 7 -- Policy impact
// --------------------------------------------------------------------------
async function PolicyPanel() {
  const result = await apiTry<PolicyImpact>("/analytics/national/policy-impact");

  if (!result.ok) {
    return (
      <Panel>
        <PanelHeader title="Policy impact" />
        <ErrorState message={result.error} />
      </Panel>
    );
  }

  const data = result.data;

  if (data.total_complaints === 0) {
    return (
      <Panel>
        <PanelHeader title="Policy impact" />
        <EmptyState
          icon={Scale}
          title="No complaints on record"
          description="Enforcement outcomes, resolution times, and repeat-offender tracking appear here once citizens have filed grievances."
        />
      </Panel>
    );
  }

  const actions = data.by_action.filter((entry) => entry.count > 0);

  return (
    <div className="grid gap-4">
      <div className="grid grid-cols-2 gap-4 xl:grid-cols-4">
        <StatTile
          label="Complaints filed"
          value={data.total_complaints}
          meta={`${data.open_complaints} still open`}
          icon={Gavel}
        />
        <StatTile
          label="Mean resolution"
          value={
            data.mean_resolution_days === null
              ? "—"
              : `${data.mean_resolution_days.toFixed(1)} d`
          }
          meta={
            data.median_resolution_days === null
              ? "Nothing closed yet"
              : `Median ${data.median_resolution_days.toFixed(1)} days`
          }
        />
        <StatTile
          label="Enforcement rate"
          value={ratioText(data.enforcement_rate)}
          meta="Closed complaints ending in an action other than dismissal"
        />
        <StatTile
          label="Repeat offenders"
          value={data.repeat_offender_count}
          meta="Drew the same complaint again after enforcement"
          tone={data.repeat_offender_count > 0 ? "warning" : "default"}
        />
      </div>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <Panel>
          <PanelHeader title="By category" />
          <div className="divide-y divide-border">
            {data.by_category.map((entry) => (
              <MetricBar
                key={entry.category}
                label={humanise(entry.category)}
                ratio={entry.count / data.total_complaints}
                valueLabel={String(entry.count)}
              />
            ))}
          </div>
        </Panel>

        <Panel>
          <PanelHeader
            title="Enforcement outcomes"
            description={`${data.closed_complaints} closed of ${data.total_complaints} filed`}
          />
          {actions.length === 0 ? (
            <EmptyState
              icon={Scale}
              title="No enforcement decisions yet"
              description="Actions appear here once an investigation has been closed with a decision recorded."
            />
          ) : (
            <TableWrap>
              <Table className="min-w-0">
                <THead>
                  <tr>
                    <TH>Action</TH>
                    <TH numeric>Count</TH>
                  </tr>
                </THead>
                <TBody>
                  {actions.map((entry) => (
                    <TR key={entry.action}>
                      <TDPrimary>{humanise(entry.action)}</TDPrimary>
                      <TD numeric>{entry.count}</TD>
                    </TR>
                  ))}
                </TBody>
              </Table>
            </TableWrap>
          )}
        </Panel>
      </div>
    </div>
  );
}
