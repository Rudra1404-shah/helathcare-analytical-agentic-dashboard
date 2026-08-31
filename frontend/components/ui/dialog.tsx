"use client";

import * as Primitive from "@radix-ui/react-dialog";
import { Loader2 } from "lucide-react";
import * as React from "react";

import { Button, type ButtonProps } from "@/components/ui/button";
import { cn } from "@/lib/cn";

/**
 * The dialog every write flow in the application opens.
 *
 * Radix supplies the parts that are tedious to get right and invisible when
 * they work: focus is trapped inside the panel, returned to the trigger on
 * close, escape closes, and the rest of the page is inert to a screen reader
 * while it is open.
 *
 * Motion is the enter transition and nothing else. At MOTION_INTENSITY 2 a
 * dialog that springs or bounces reads as unserious; see DESIGN.md section 7.
 * The scrim is a flat tint rather than a blur, because glassmorphism is banned
 * and a blurred ward list behind a form is harder to read, not easier.
 */

export const DialogRoot = Primitive.Root;
export const DialogTrigger = Primitive.Trigger;
export const DialogClose = Primitive.Close;

const WIDTHS = {
  sm: "w-[min(26rem,calc(100vw-2rem))]",
  md: "w-[min(32rem,calc(100vw-2rem))]",
  lg: "w-[min(44rem,calc(100vw-2rem))]",
} as const;

export type DialogSize = keyof typeof WIDTHS;

/** The panel itself. Use `FormDialog` unless a flow genuinely is not a form. */
export function DialogPanel({
  title,
  description,
  size = "md",
  className,
  children,
}: {
  title: string;
  description?: React.ReactNode;
  size?: DialogSize;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <Primitive.Portal>
      <Primitive.Overlay className="dialog-overlay fixed inset-0 z-40 bg-slate-950/40" />
      <Primitive.Content
        className={cn(
          "dialog-panel fixed left-1/2 top-1/2 z-50 -translate-x-1/2 -translate-y-1/2",
          "max-h-[calc(100dvh-3rem)] overflow-y-auto rounded-lg border border-border",
          "bg-surface p-5 shadow-lg",
          WIDTHS[size],
          className,
        )}
      >
        <Primitive.Title className="text-sm font-semibold text-foreground">
          {title}
        </Primitive.Title>
        {description ? (
          <Primitive.Description className="mt-1 text-sm text-muted-foreground">
            {description}
          </Primitive.Description>
        ) : (
          // Radix warns when a dialog has no description. An empty one is
          // still correct here: the title carries the whole meaning.
          <Primitive.Description className="sr-only">{title}</Primitive.Description>
        )}
        {children}
      </Primitive.Content>
    </Primitive.Portal>
  );
}

/** What every server action in this application returns. */
export interface ActionResult {
  ok: boolean;
  error?: string;
}

interface FormDialogProps<R extends ActionResult> {
  trigger: React.ReactNode;
  title: string;
  description?: React.ReactNode;
  size?: DialogSize;
  submitLabel: string;
  pendingLabel?: string;
  submitVariant?: ButtonProps["variant"];
  cancelLabel?: string;
  /** Bound server action. The dialog supplies the form data. */
  action: (formData: FormData) => Promise<R>;
  /** Runs after a successful call, before the dialog closes. */
  onSuccess?: (result: R) => void;
  /** Guard that runs before the call, so an obvious mistake costs no round trip. */
  validate?: (formData: FormData) => string | null;
  children: React.ReactNode | ((state: { pending: boolean }) => React.ReactNode);
}

/**
 * A dialog wrapping a form that calls a server action.
 *
 * The error is rendered inside the panel, next to the fields that caused it,
 * rather than in a corner toast: the person who has to fix it is looking at
 * the form. Success is what gets announced elsewhere, because by then the
 * dialog is gone.
 */
export function FormDialog<R extends ActionResult>({
  trigger,
  title,
  description,
  size = "md",
  submitLabel,
  pendingLabel = "Saving",
  submitVariant = "primary",
  cancelLabel = "Cancel",
  action,
  onSuccess,
  validate,
  children,
}: FormDialogProps<R>) {
  const [open, setOpen] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [pending, startTransition] = React.useTransition();

  // A reopened dialog must not still be showing the last attempt's failure.
  function handleOpenChange(next: boolean) {
    if (pending) return;
    setOpen(next);
    if (!next) setError(null);
  }

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);

    const objection = validate?.(formData) ?? null;
    if (objection) {
      setError(objection);
      return;
    }

    setError(null);
    startTransition(async () => {
      const result = await action(formData);
      if (result.ok) {
        onSuccess?.(result);
        setOpen(false);
      } else {
        setError(result.error ?? "The change could not be saved.");
      }
    });
  }

  return (
    <DialogRoot open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogPanel title={title} description={description} size={size}>
        <form onSubmit={handleSubmit} className="mt-4 flex flex-col gap-4">
          {typeof children === "function" ? children({ pending }) : children}

          {error ? (
            <p
              role="alert"
              className="rounded-md bg-critical-muted px-3 py-2 text-sm text-critical"
            >
              {error}
            </p>
          ) : null}

          <div className="flex justify-end gap-2">
            <DialogClose asChild>
              <Button type="button" variant="secondary" disabled={pending}>
                {cancelLabel}
              </Button>
            </DialogClose>
            <Button type="submit" variant={submitVariant} disabled={pending}>
              {pending ? (
                <>
                  <Loader2 className="animate-spin" strokeWidth={1.75} aria-hidden="true" />
                  {pendingLabel}
                </>
              ) : (
                submitLabel
              )}
            </Button>
          </div>
        </form>
      </DialogPanel>
    </DialogRoot>
  );
}
