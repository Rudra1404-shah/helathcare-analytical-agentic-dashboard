import { AlertTriangle, Bed, HeartPulse, Wind } from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { Panel } from "@/components/ui/panel";
import { cn } from "@/lib/cn";
import { humanise, percent, quantity } from "@/lib/format";
import type { CapacityCard, InventoryCategory } from "@/lib/types";

const ICONS: Partial<Record<InventoryCategory, LucideIcon>> = {
  GENERAL_BEDS: Bed,
  ICU_BEDS: HeartPulse,
  VENTILATORS: Wind,
  OXYGEN_LITERS: Wind,
};

const LABELS: Partial<Record<InventoryCategory, string>> = {
  GENERAL_BEDS: "General beds",
  ICU_BEDS: "ICU beds",
  VENTILATORS: "Ventilators",
  OXYGEN_LITERS: "Oxygen",
};

/**
 * The live capacity row on the hospital overview.
 *
 * The number that matters is what is *free*, so that is the one rendered at
 * display size. Utilisation is shown as a thin bar without a filled track,
 * because a heavy grey track on every card turns a glanceable row into a
 * chart nobody reads.
 */
export function CapacityCards({ cards }: { cards: CapacityCard[] }) {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
      {cards.map((card) => (
        <CapacityTile key={card.category} card={card} />
      ))}
    </div>
  );
}

function CapacityTile({ card }: { card: CapacityCard }) {
  const Icon = ICONS[card.category] ?? Bed;
  const label = LABELS[card.category] ?? humanise(card.category);
  const untracked = card.line_count === 0;
  const critical = card.is_below_threshold;

  return (
    <Panel className={cn("p-4", critical && "border-critical")}>
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Icon
            className="size-4 text-muted-foreground"
            strokeWidth={1.75}
            aria-hidden="true"
          />
          <h3 className="text-sm font-medium text-foreground">{label}</h3>
        </div>
        {critical ? (
          <span className="flex items-center gap-1 text-xs font-medium text-critical">
            <AlertTriangle className="size-3.5" strokeWidth={1.75} aria-hidden="true" />
            Below threshold
          </span>
        ) : null}
      </div>

      {untracked ? (
        <p className="mt-3 text-sm text-muted-foreground">
          Not tracked. Add a stock line to see live availability here.
        </p>
      ) : (
        <>
          <p className="mt-3 flex items-baseline gap-1.5">
            <span
              className={cn(
                "font-mono text-3xl font-semibold tabular-nums",
                critical ? "text-critical" : "text-foreground",
              )}
            >
              {Number.isInteger(card.available_stock)
                ? card.available_stock
                : card.available_stock.toFixed(0)}
            </span>
            <span className="text-sm text-muted-foreground">
              free of {quantity(card.total_stock, card.unit)}
            </span>
          </p>

          <div className="mt-3 flex items-center gap-2">
            <div
              className="h-1 flex-1 overflow-hidden rounded-full bg-border"
              role="img"
              aria-label={`${percent(card.utilisation_ratio)} in use`}
            >
              <div
                className={cn("h-full", critical ? "bg-critical" : "bg-primary")}
                style={{ width: `${Math.min(100, card.utilisation_ratio * 100)}%` }}
              />
            </div>
            <span className="font-mono text-xs tabular-nums text-muted-foreground">
              {percent(card.utilisation_ratio)} in use
            </span>
          </div>
        </>
      )}
    </Panel>
  );
}
