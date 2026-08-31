import { Minus, TrendingDown, TrendingUp, type LucideIcon } from "lucide-react";
import type * as React from "react";

import { Badge } from "@/components/ui/badge";
import { Panel } from "@/components/ui/panel";
import { cn } from "@/lib/cn";
import { percent } from "@/lib/format";
import type { AlertTier, SignalConfidence, TrendDirection } from "@/lib/types";

/**
 * The small pieces both intelligence views are built from.
 *
 * There is no charting library in this project and this is not the place to add
 * one: DESIGN.md sets VISUAL_DENSITY to 8 and bans decorative cards, so the
 * existing idiom is a large monospaced figure with a thin unfilled bar under it
 * (see `capacity-cards.tsx`). These extend that idiom rather than introducing a
 * second visual language for the same kind of data.
 *
 * Every ratio here accepts `null` and renders it as "not available", never as
 * zero. The backend distinguishes the two deliberately and collapsing them in
 * the view would undo that on the last hop.
 */

const NOT_AVAILABLE = "—";

// --------------------------------------------------------------------------
// Figures
// --------------------------------------------------------------------------

/** A headline number with its label. The primary unit of both dashboards. */
export function StatTile({
  label,
  value,
  meta,
  icon: Icon,
  tone = "default",
}: {
  label: string;
  value: React.ReactNode;
  meta?: React.ReactNode;
  icon?: LucideIcon;
  tone?: "default" | "critical" | "warning";
}) {
  return (
    <Panel className={cn("p-4", tone === "critical" && "border-critical")}>
      <div className="flex items-center gap-2">
        {Icon ? (
          <Icon
            className="size-4 text-muted-foreground"
            strokeWidth={1.75}
            aria-hidden="true"
          />
        ) : null}
        <h3 className="text-sm font-medium text-foreground">{label}</h3>
      </div>
      <p
        className={cn(
          "mt-3 font-mono text-3xl font-semibold tabular-nums",
          tone === "critical" && "text-critical",
          tone === "warning" && "text-warning",
          tone === "default" && "text-foreground",
        )}
      >
        {value}
      </p>
      {meta ? <p className="mt-1.5 text-xs text-muted-foreground">{meta}</p> : null}
    </Panel>
  );
}

/**
 * A labelled ratio with a thin bar, used for occupancy gauges and burnout.
 *
 * The bar is capped at 100% of its track while the figure beside it is not, so
 * a doctor at 180% of their ceiling reads as a full bar next to "180%" rather
 * than silently overflowing the row.
 */
export function MetricBar({
  label,
  meta,
  ratio,
  tone,
  valueLabel,
}: {
  label: React.ReactNode;
  meta?: React.ReactNode;
  ratio: number | null;
  tone?: "critical" | "warning" | "default";
  valueLabel?: string;
}) {
  const resolvedTone = tone ?? toneForRatio(ratio);
  const display = valueLabel ?? (ratio === null ? NOT_AVAILABLE : percent(ratio));

  return (
    <div className="px-4 py-3">
      <div className="flex items-baseline justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate text-sm font-medium text-foreground">{label}</p>
          {meta ? (
            <p className="mt-0.5 text-xs text-muted-foreground">{meta}</p>
          ) : null}
        </div>
        <span
          className={cn(
            "shrink-0 font-mono text-sm font-medium tabular-nums",
            resolvedTone === "critical" && "text-critical",
            resolvedTone === "warning" && "text-warning",
            resolvedTone === "default" && "text-foreground",
          )}
        >
          {display}
        </span>
      </div>
      <div
        className="mt-2 h-1 overflow-hidden rounded-full bg-border"
        role="img"
        aria-label={ratio === null ? `${label}: not available` : `${label}: ${display}`}
      >
        {ratio === null ? null : (
          <div
            className={cn(
              "h-full",
              resolvedTone === "critical" && "bg-critical",
              resolvedTone === "warning" && "bg-warning",
              resolvedTone === "default" && "bg-primary",
            )}
            style={{ width: `${Math.min(100, Math.max(0, ratio * 100))}%` }}
          />
        )}
      </div>
    </div>
  );
}

function toneForRatio(ratio: number | null): "critical" | "warning" | "default" {
  if (ratio === null) return "default";
  if (ratio >= 0.9) return "critical";
  if (ratio >= 0.75) return "warning";
  return "default";
}

/** Render a nullable ratio as a percentage, or an em dash when undefined. */
export function ratioText(ratio: number | null): string {
  return ratio === null ? NOT_AVAILABLE : percent(ratio);
}

/** Render a nullable day count, keeping one decimal where it is meaningful. */
export function daysText(days: number | null): string {
  if (days === null) return NOT_AVAILABLE;
  if (days === 0) return "0";
  return days >= 10 ? String(Math.round(days)) : days.toFixed(1);
}

// --------------------------------------------------------------------------
// Labels
// --------------------------------------------------------------------------

const TIER_TONE = {
  CRITICAL: "critical",
  HIGH: "warning",
  MEDIUM: "info",
  INFO: "neutral",
} as const;

const TIER_LABEL: Record<AlertTier, string> = {
  CRITICAL: "Critical",
  HIGH: "High",
  MEDIUM: "Medium",
  INFO: "Info",
};

/** An alert's severity. Always carries text; colour is never the only signal. */
export function AlertTierBadge({ tier }: { tier: AlertTier }) {
  return <Badge tone={TIER_TONE[tier]}>{TIER_LABEL[tier]}</Badge>;
}

const CONFIDENCE_LABEL: Record<SignalConfidence, string> = {
  HIGH: "High confidence",
  MODERATE: "Moderate confidence",
  LOW: "Low confidence",
  INSUFFICIENT_DATA: "Not enough history",
};

const CONFIDENCE_TONE = {
  HIGH: "stable",
  MODERATE: "info",
  LOW: "warning",
  INSUFFICIENT_DATA: "neutral",
} as const;

/**
 * How much weight an analytical figure can carry.
 *
 * Shown next to every inferred number. A dashboard that cannot tell a
 * measurement from an extrapolation will eventually present one as the other.
 */
export function ConfidenceBadge({ confidence }: { confidence: SignalConfidence }) {
  return <Badge tone={CONFIDENCE_TONE[confidence]}>{CONFIDENCE_LABEL[confidence]}</Badge>;
}

const TREND_ICON: Record<TrendDirection, LucideIcon> = {
  RISING: TrendingUp,
  FALLING: TrendingDown,
  STABLE: Minus,
};

const TREND_LABEL: Record<TrendDirection, string> = {
  RISING: "Rising",
  FALLING: "Falling",
  STABLE: "Stable",
};

/** Which way a fitted series is moving, as an icon plus its word. */
export function TrendIndicator({
  direction,
  perDay,
}: {
  direction: TrendDirection;
  perDay: number;
}) {
  const Icon = TREND_ICON[direction];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 text-sm",
        direction === "RISING" ? "text-critical" : "text-muted-foreground",
      )}
    >
      <Icon className="size-4" strokeWidth={1.75} aria-hidden="true" />
      {TREND_LABEL[direction]}
      <span className="font-mono text-xs tabular-nums">
        {perDay >= 0 ? "+" : ""}
        {perDay.toFixed(2)}/day
      </span>
    </span>
  );
}
