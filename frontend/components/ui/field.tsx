import type * as React from "react";

import { cn } from "@/lib/cn";
import { FieldError } from "@/components/ui/states";

/**
 * Form controls.
 *
 * The label is always above the input and always present. Placeholder-as-label
 * disappears the moment somebody types, which is exactly when they most need to
 * know what the field is. Required fields are marked in the label text, not by
 * colour alone.
 */

export function Field({
  label,
  htmlFor,
  hint,
  error,
  required,
  className,
  children,
}: {
  label: string;
  htmlFor: string;
  hint?: string;
  error?: string | null;
  required?: boolean;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div className={cn("flex flex-col gap-1.5", className)}>
      <label htmlFor={htmlFor} className="text-sm font-medium text-foreground">
        {label}
        {required ? (
          <span className="ml-1 text-xs font-normal text-muted-foreground">(required)</span>
        ) : null}
      </label>
      {hint ? <p className="text-xs text-muted-foreground">{hint}</p> : null}
      {children}
      <FieldError message={error} />
    </div>
  );
}

const CONTROL =
  "h-9 w-full rounded-md border border-border bg-surface px-3 text-sm text-foreground " +
  "placeholder:text-muted-foreground transition-colors duration-150 " +
  "disabled:cursor-not-allowed disabled:opacity-60";

export function Input({ className, ...props }: React.InputHTMLAttributes<HTMLInputElement>) {
  return <input className={cn(CONTROL, className)} {...props} />;
}

export function Textarea({
  className,
  ...props
}: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      className={cn(CONTROL, "h-auto min-h-24 py-2 leading-relaxed", className)}
      {...props}
    />
  );
}

export function Select({
  className,
  children,
  ...props
}: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select className={cn(CONTROL, "pr-8", className)} {...props}>
      {children}
    </select>
  );
}

/** A compact select for filter bars, where the label sits inline. */
export function FilterSelect({
  label,
  className,
  children,
  ...props
}: React.SelectHTMLAttributes<HTMLSelectElement> & { label: string }) {
  const id = `filter-${props.name ?? label.toLowerCase().replace(/\s+/g, "-")}`;
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="text-xs font-medium text-muted-foreground">
        {label}
      </label>
      <select
        id={id}
        className={cn(
          "h-8 rounded-md border border-border bg-surface px-2 pr-7 text-sm text-foreground",
          "transition-colors duration-150",
          className,
        )}
        {...props}
      >
        {children}
      </select>
    </div>
  );
}
