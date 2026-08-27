import type * as React from "react";

import { cn } from "@/lib/cn";

/**
 * The primary component of this system.
 *
 * Wide tables scroll inside their own container so the page body never scrolls
 * horizontally. Numeric columns are right-aligned and monospaced, because a
 * column of numbers that does not align on the decimal cannot be compared down
 * the column, which is the only reason the column exists.
 */

export function TableWrap({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("w-full overflow-x-auto", className)} {...props} />;
}

export function Table({ className, ...props }: React.TableHTMLAttributes<HTMLTableElement>) {
  return (
    <table
      className={cn("w-full min-w-[42rem] caption-bottom border-collapse text-sm", className)}
      {...props}
    />
  );
}

export function THead({ className, ...props }: React.HTMLAttributes<HTMLTableSectionElement>) {
  return (
    <thead
      className={cn("sticky top-0 z-10 bg-surface-muted text-muted-foreground", className)}
      {...props}
    />
  );
}

export function TBody({ className, ...props }: React.HTMLAttributes<HTMLTableSectionElement>) {
  return <tbody className={cn("divide-y divide-border", className)} {...props} />;
}

export function TR({ className, ...props }: React.HTMLAttributes<HTMLTableRowElement>) {
  return (
    <tr
      className={cn("transition-colors duration-150 hover:bg-surface-muted", className)}
      {...props}
    />
  );
}

export function TH({
  className,
  numeric,
  ...props
}: React.ThHTMLAttributes<HTMLTableCellElement> & { numeric?: boolean }) {
  return (
    <th
      scope="col"
      className={cn(
        "px-4 py-2.5 text-left text-xs font-medium uppercase tracking-wide",
        numeric && "text-right",
        className,
      )}
      {...props}
    />
  );
}

export function TD({
  className,
  numeric,
  ...props
}: React.TdHTMLAttributes<HTMLTableCellElement> & { numeric?: boolean }) {
  return (
    <td
      className={cn(
        "h-11 px-4 align-middle",
        numeric && "text-right font-mono tabular-nums",
        className,
      )}
      {...props}
    />
  );
}

/** A primary identifier cell: the thing the row is about. */
export function TDPrimary({
  className,
  ...props
}: React.TdHTMLAttributes<HTMLTableCellElement>) {
  return <TD className={cn("font-medium text-foreground", className)} {...props} />;
}

/** Secondary metadata under a primary cell. */
export function TDMeta({ children }: { children: React.ReactNode }) {
  return <div className="text-xs font-normal text-muted-foreground">{children}</div>;
}
