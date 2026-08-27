import { AlertTriangle, Inbox, type LucideIcon } from "lucide-react";
import type * as React from "react";

import { cn } from "@/lib/cn";
import { Panel } from "@/components/ui/panel";

/**
 * The three states every asynchronous view owes beyond its data.
 *
 * A view that renders only its loaded state is unfinished: the first request
 * on a cold connection shows nothing, an empty register looks broken, and a
 * failed call shows a blank page with no way forward.
 */

// --------------------------------------------------------------------------
// Loading
// --------------------------------------------------------------------------

/** A single shimmering placeholder. Shape it like what it stands in for. */
export function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("skeleton rounded-md", className)} {...props} />;
}

/** A skeleton shaped like the table it replaces, so nothing shifts on load. */
export function TableSkeleton({ rows = 8, columns = 5 }: { rows?: number; columns?: number }) {
  return (
    <div role="status" aria-label="Loading records" className="divide-y divide-border">
      <div className="flex gap-4 bg-surface-muted px-4 py-2.5">
        {Array.from({ length: columns }).map((_, index) => (
          <Skeleton key={index} className="h-3 flex-1" />
        ))}
      </div>
      {Array.from({ length: rows }).map((_, row) => (
        <div key={row} className="flex items-center gap-4 px-4 py-3">
          {Array.from({ length: columns }).map((_, column) => (
            <Skeleton
              key={column}
              className={cn("h-4 flex-1", column === 0 && "max-w-[22ch]")}
            />
          ))}
        </div>
      ))}
    </div>
  );
}

/** A skeleton row of metric cards. */
export function CardsSkeleton({ count = 4 }: { count?: number }) {
  return (
    <div
      role="status"
      aria-label="Loading capacity"
      className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4"
    >
      {Array.from({ length: count }).map((_, index) => (
        <Panel key={index} className="p-4">
          <Skeleton className="h-3 w-24" />
          <Skeleton className="mt-3 h-8 w-32" />
          <Skeleton className="mt-3 h-2 w-full" />
        </Panel>
      ))}
    </div>
  );
}

// --------------------------------------------------------------------------
// Empty
// --------------------------------------------------------------------------

/**
 * An empty state names what would populate it and offers the way to do it.
 * "No results" with a shrug is not an empty state, it is a dead end.
 */
export function EmptyState({
  icon: Icon = Inbox,
  title,
  description,
  action,
}: {
  icon?: LucideIcon;
  title: string;
  description: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col items-center px-6 py-14 text-center">
      <Icon
        className="size-6 text-muted-foreground"
        strokeWidth={1.75}
        aria-hidden="true"
      />
      <h3 className="mt-3 text-sm font-semibold text-foreground">{title}</h3>
      <p className="mt-1 max-w-[46ch] text-sm text-muted-foreground">{description}</p>
      {action ? <div className="mt-4">{action}</div> : null}
    </div>
  );
}

// --------------------------------------------------------------------------
// Error
// --------------------------------------------------------------------------

/**
 * The message shown is the API's own. The platform writes its errors for a
 * human to read, so replacing them with "Something went wrong" would discard
 * the only useful part.
 */
export function ErrorState({
  message,
  action,
}: {
  message: string;
  action?: React.ReactNode;
}) {
  return (
    <div
      role="alert"
      className="flex flex-col items-center px-6 py-14 text-center"
    >
      <AlertTriangle className="size-6 text-critical" strokeWidth={1.75} aria-hidden="true" />
      <h3 className="mt-3 text-sm font-semibold text-foreground">
        This could not be loaded
      </h3>
      <p className="mt-1 max-w-[52ch] text-sm text-muted-foreground">{message}</p>
      {action ? <div className="mt-4">{action}</div> : null}
    </div>
  );
}

/** Inline form error, rendered under the field it belongs to. */
export function FieldError({ message }: { message?: string | null }) {
  if (!message) return null;
  return (
    <p role="alert" className="mt-1.5 text-xs text-critical">
      {message}
    </p>
  );
}
