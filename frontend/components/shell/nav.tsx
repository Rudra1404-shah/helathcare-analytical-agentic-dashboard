"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { Menu, X } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

import type { NavSection } from "@/components/shell/app-shell";
import { NAV_ICONS } from "@/components/shell/nav-icons";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/cn";

function isActive(pathname: string, href: string, exact?: boolean): boolean {
  if (exact) return pathname === href;
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function NavList({
  sections,
  onNavigate,
}: {
  sections: NavSection[];
  onNavigate?: () => void;
}) {
  const pathname = usePathname();

  return (
    <nav aria-label="Portal sections" className="flex flex-col gap-5">
      {sections.map((section) => (
        <div key={section.heading}>
          <h2 className="px-2 pb-1.5 text-xs font-medium uppercase tracking-wide text-muted-foreground">
            {section.heading}
          </h2>
          <ul className="flex flex-col gap-0.5">
            {section.items.map((item) => {
              const Icon = NAV_ICONS[item.icon];
              const active = isActive(pathname, item.href, item.exact);
              return (
                <li key={item.href}>
                  <Link
                    href={item.href}
                    onClick={onNavigate}
                    aria-current={active ? "page" : undefined}
                    className={cn(
                      "flex items-center gap-2.5 rounded-md px-2 py-2 text-sm",
                      "transition-colors duration-150",
                      active
                        ? "bg-primary-muted font-medium text-primary"
                        : "text-foreground hover:bg-surface-muted",
                    )}
                  >
                    <Icon className="size-4 shrink-0" strokeWidth={1.75} aria-hidden="true" />
                    <span className="truncate">{item.label}</span>
                  </Link>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </nav>
  );
}

/**
 * Below `lg` the sidebar becomes a sheet. Radix handles the focus trap and
 * restores focus to the trigger on close.
 */
export function SidebarSheet({
  sections,
  portal,
}: {
  sections: NavSection[];
  portal: string;
}) {
  const pathname = usePathname();

  // Keyed by route so navigating remounts the sheet closed. Resetting the flag
  // inside an effect instead would fire a second render on every navigation,
  // and would leave the sheet briefly open over the new page.
  return <Sheet key={pathname} sections={sections} portal={portal} />;
}

function Sheet({ sections, portal }: { sections: NavSection[]; portal: string }) {
  const [open, setOpen] = useState(false);

  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <Dialog.Trigger asChild>
        <Button variant="ghost" size="icon" className="lg:hidden" aria-label="Open navigation">
          <Menu strokeWidth={1.75} aria-hidden="true" />
        </Button>
      </Dialog.Trigger>

      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-slate-950/40 lg:hidden" />
        <Dialog.Content className="fixed inset-y-0 left-0 z-50 w-72 overflow-y-auto border-r border-border bg-surface p-4 shadow-lg lg:hidden">
          <div className="mb-4 flex items-center justify-between">
            <Dialog.Title className="text-sm font-semibold text-foreground">
              {portal}
            </Dialog.Title>
            <Dialog.Close asChild>
              <Button variant="ghost" size="icon" aria-label="Close navigation">
                <X strokeWidth={1.75} aria-hidden="true" />
              </Button>
            </Dialog.Close>
          </div>
          <Dialog.Description className="sr-only">
            Navigate between sections of the {portal}.
          </Dialog.Description>
          <NavList sections={sections} onNavigate={() => setOpen(false)} />
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
