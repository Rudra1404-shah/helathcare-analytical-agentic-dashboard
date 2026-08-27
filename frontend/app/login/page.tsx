import { Activity } from "lucide-react";
import type { Metadata } from "next";

import { LoginForm } from "@/app/login/login-form";

export const metadata: Metadata = { title: "Sign in" };

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ next?: string }>;
}) {
  const { next } = await searchParams;

  return (
    <main
      id="main"
      className="flex min-h-[100dvh] items-center justify-center bg-background px-4 py-12"
    >
      <div className="w-full max-w-md">
        <div className="mb-8 flex items-center gap-2.5">
          <Activity className="size-6 text-primary" strokeWidth={1.75} aria-hidden="true" />
          <span className="text-sm font-semibold tracking-tight text-foreground">
            Unified National Health Platform
          </span>
        </div>

        <h1 className="text-xl font-semibold tracking-tight text-foreground">Sign in</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Choose the portal your account belongs to.
        </p>

        <LoginForm nextPath={next} />
      </div>
    </main>
  );
}
