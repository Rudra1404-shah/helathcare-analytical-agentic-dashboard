"use client";

import { Building2, Landmark, Loader2, Users } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/field";
import { Panel } from "@/components/ui/panel";
import { cn } from "@/lib/cn";

type Portal = "government" | "hospital" | "citizen";

const PORTALS: { id: Portal; label: string; hint: string; icon: typeof Landmark }[] = [
  {
    id: "government",
    label: "Government",
    hint: "Health Ministry officials",
    icon: Landmark,
  },
  {
    id: "hospital",
    label: "Hospital",
    hint: "Admins, staff, and doctors",
    icon: Building2,
  },
  { id: "citizen", label: "Citizen", hint: "Public health record access", icon: Users },
];

export function LoginForm({ nextPath }: { nextPath?: string }) {
  const router = useRouter();
  const [portal, setPortal] = useState<Portal>("government");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setPending(true);

    const form = new FormData(event.currentTarget);
    try {
      const response = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: String(form.get("email") ?? ""),
          password: String(form.get("password") ?? ""),
          portal,
        }),
      });

      const body = (await response.json()) as { error?: string; landing?: string };
      if (!response.ok) {
        setError(body.error ?? "Sign-in failed.");
        setPending(false);
        return;
      }

      router.push(nextPath ?? body.landing ?? "/");
      router.refresh();
    } catch {
      setError("The sign-in request could not be sent. Check your connection.");
      setPending(false);
    }
  }

  return (
    <Panel className="mt-6 p-5">
      <fieldset>
        <legend className="text-sm font-medium text-foreground">Portal</legend>
        <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-3">
          {PORTALS.map((option) => {
            const Icon = option.icon;
            const active = portal === option.id;
            return (
              <button
                key={option.id}
                type="button"
                onClick={() => setPortal(option.id)}
                aria-pressed={active}
                className={cn(
                  "flex flex-col items-start gap-1 rounded-md border px-3 py-2.5 text-left",
                  "transition-colors duration-150 active:scale-[0.98]",
                  active
                    ? "border-primary bg-primary-muted"
                    : "border-border bg-surface hover:bg-surface-muted",
                )}
              >
                <Icon
                  className={cn("size-4", active ? "text-primary" : "text-muted-foreground")}
                  strokeWidth={1.75}
                  aria-hidden="true"
                />
                <span className="text-sm font-medium text-foreground">{option.label}</span>
                <span className="text-xs text-muted-foreground">{option.hint}</span>
              </button>
            );
          })}
        </div>
      </fieldset>

      <form onSubmit={handleSubmit} className="mt-5 flex flex-col gap-4">
        <Field label="Email address" htmlFor="email" required>
          <Input
            id="email"
            name="email"
            type="email"
            autoComplete="username"
            required
            disabled={pending}
          />
        </Field>

        <Field label="Password" htmlFor="password" required>
          <Input
            id="password"
            name="password"
            type="password"
            autoComplete="current-password"
            required
            disabled={pending}
          />
        </Field>

        {error ? (
          <p
            role="alert"
            className="rounded-md bg-critical-muted px-3 py-2 text-sm text-critical"
          >
            {error}
          </p>
        ) : null}

        <Button type="submit" disabled={pending} className="w-full">
          {pending ? (
            <>
              <Loader2 className="animate-spin" strokeWidth={1.75} aria-hidden="true" />
              Signing in
            </>
          ) : (
            "Sign in"
          )}
        </Button>
      </form>

      <p className="mt-4 border-t border-border pt-4 text-xs text-muted-foreground">
        New citizen?{" "}
        <a href="/register" className="text-primary underline-offset-4 hover:underline">
          Create an account
        </a>{" "}
        to access your health record and file a complaint.
      </p>
    </Panel>
  );
}
