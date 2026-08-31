"use client";

import * as Primitive from "@radix-ui/react-toast";
import { Check } from "lucide-react";
import * as React from "react";

/**
 * Success confirmations.
 *
 * Only success is announced here. A failure is rendered inside the form that
 * caused it, where the person who has to correct it is already looking; a
 * toast in the corner is the wrong place for something that needs acting on.
 *
 * The viewport is a polite live region, so a nurse using a screen reader hears
 * "Vitals recorded" without losing their place in the register.
 */

interface ToastContextValue {
  /** Announce a completed write. Keep it to what changed, in past tense. */
  confirm: (message: string) => void;
}

const ToastContext = React.createContext<ToastContextValue | null>(null);

/**
 * Read the confirmation channel.
 *
 * Returns a no-op outside a provider rather than throwing: a missing toast is
 * never a reason to take down a ward screen that is otherwise working.
 */
export function useToast(): ToastContextValue {
  const value = React.useContext(ToastContext);
  return value ?? FALLBACK;
}

const FALLBACK: ToastContextValue = { confirm: () => undefined };

interface Entry {
  id: number;
  message: string;
}

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [entries, setEntries] = React.useState<Entry[]>([]);
  const nextId = React.useRef(0);

  const confirm = React.useCallback((message: string) => {
    nextId.current += 1;
    setEntries((current) => [...current, { id: nextId.current, message }]);
  }, []);

  const dismiss = React.useCallback((id: number) => {
    setEntries((current) => current.filter((entry) => entry.id !== id));
  }, []);

  const value = React.useMemo(() => ({ confirm }), [confirm]);

  return (
    <ToastContext.Provider value={value}>
      <Primitive.Provider duration={4000} swipeDirection="right">
        {children}

        {entries.map((entry) => (
          <Primitive.Root
            key={entry.id}
            open
            onOpenChange={(open) => {
              if (!open) dismiss(entry.id);
            }}
            className="toast-root flex items-center gap-2.5 rounded-md border border-border bg-surface px-3.5 py-2.5 shadow-lg"
          >
            <Check
              className="size-4 shrink-0 text-stable"
              strokeWidth={1.75}
              aria-hidden="true"
            />
            <Primitive.Title className="text-sm text-foreground">
              {entry.message}
            </Primitive.Title>
          </Primitive.Root>
        ))}

        <Primitive.Viewport className="fixed bottom-4 right-4 z-[60] flex w-[min(24rem,calc(100vw-2rem))] flex-col gap-2 outline-none" />
      </Primitive.Provider>
    </ToastContext.Provider>
  );
}
