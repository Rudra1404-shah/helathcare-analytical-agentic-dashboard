import { Activity, LogOut } from "lucide-react";
import type * as React from "react";

import { NavList, SidebarSheet } from "@/components/shell/nav";
import type { NavIconName } from "@/components/shell/nav-icons";
import { Button } from "@/components/ui/button";
import { initials } from "@/lib/format";
import type { SessionUser } from "@/lib/types";

export interface NavItem {
  href: string;
  label: string;
  /**
   * Named rather than imported directly: a component reference cannot cross
   * the server-to-client boundary, and the sidebar is a Client Component.
   */
  icon: NavIconName;
  /** Match only the exact path. Used for a portal's index route. */
  exact?: boolean;
}

export interface NavSection {
  heading: string;
  items: NavItem[];
}

/**
 * The frame every portal renders inside: 64px top bar, 240px sidebar, content.
 *
 * Identical grammar in all three portals so muscle memory transfers. Below
 * `lg` the sidebar becomes a sheet rather than collapsing to icons, because an
 * icon rail without labels is a memory test.
 */
export function AppShell({
  portal,
  sections,
  user,
  contextLabel,
  children,
}: {
  portal: string;
  sections: NavSection[];
  user: SessionUser | null;
  contextLabel?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="min-h-[100dvh] bg-background">
      <header className="sticky top-0 z-30 flex h-16 items-center gap-3 border-b border-border bg-surface px-4 lg:px-6">
        <SidebarSheet sections={sections} portal={portal} />

        <div className="flex min-w-0 items-center gap-2.5">
          <Activity className="size-5 shrink-0 text-primary" strokeWidth={1.75} aria-hidden="true" />
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold tracking-tight text-foreground">
              {portal}
            </p>
            {contextLabel ? (
              <p className="truncate text-xs text-muted-foreground">{contextLabel}</p>
            ) : null}
          </div>
        </div>

        <div className="ml-auto flex items-center gap-3">
          {user ? (
            <div className="hidden items-center gap-2.5 sm:flex">
              <span
                aria-hidden="true"
                className="grid size-8 place-items-center rounded-md bg-surface-muted text-xs font-semibold text-foreground"
              >
                {initials(user.full_name)}
              </span>
              <div className="text-right">
                <p className="text-sm font-medium leading-tight text-foreground">
                  {user.full_name}
                </p>
                <p className="text-xs leading-tight text-muted-foreground">{user.email}</p>
              </div>
            </div>
          ) : null}

          <form action="/api/auth/logout" method="post">
            <Button type="submit" variant="secondary" size="sm">
              <LogOut strokeWidth={1.75} aria-hidden="true" />
              Sign out
            </Button>
          </form>
        </div>
      </header>

      <div className="flex">
        <aside className="sticky top-16 hidden h-[calc(100dvh-4rem)] w-60 shrink-0 overflow-y-auto border-r border-border bg-surface px-3 py-4 lg:block">
          <NavList sections={sections} />
        </aside>

        <main id="main" className="min-w-0 flex-1">
          <div className="mx-auto max-w-[1400px] px-4 py-6 lg:px-6">{children}</div>
        </main>
      </div>
    </div>
  );
}
