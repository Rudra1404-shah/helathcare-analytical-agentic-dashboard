import { ShieldCheck } from "lucide-react";

import { AlertTierBadge } from "@/components/data/analytics-primitives";
import { EmptyState } from "@/components/ui/states";
import { cn } from "@/lib/cn";
import type { SmartAlert } from "@/lib/types";

/**
 * The four-tier action list.
 *
 * Every row carries its recommended action, because an alert nobody can act on
 * is noise, and the severity is spelled out in words beside its colour so the
 * list is readable without relying on hue.
 */
export function AlertList({ alerts }: { alerts: SmartAlert[] }) {
  if (alerts.length === 0) {
    return (
      <EmptyState
        icon={ShieldCheck}
        title="Nothing needs attention"
        description="No occupancy, stock, workforce, or outbreak threshold has been crossed. Alerts appear here the moment one is."
      />
    );
  }

  return (
    <ul className="divide-y divide-border">
      {alerts.map((alert, index) => (
        <li
          key={`${alert.kind}-${alert.title}-${index}`}
          className={cn(
            "px-4 py-3",
            alert.tier === "CRITICAL" && "border-l-2 border-l-critical",
          )}
        >
          <div className="flex flex-wrap items-start justify-between gap-2">
            <p className="text-sm font-medium text-foreground">{alert.title}</p>
            <AlertTierBadge tier={alert.tier} />
          </div>
          <p className="mt-1 text-xs text-muted-foreground">{alert.detail}</p>
          <p className="mt-1.5 text-xs text-foreground">
            <span className="text-muted-foreground">Action: </span>
            {alert.recommended_action}
          </p>
        </li>
      ))}
    </ul>
  );
}
