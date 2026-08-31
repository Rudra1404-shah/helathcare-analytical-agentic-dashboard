import Link from "next/link";

import { cn } from "@/lib/cn";

/**
 * A segmented control built from links rather than client-side tab state.
 *
 * Three reasons it is not a Radix `Tabs`. The page stays a Server Component, so
 * no JavaScript ships for what is fundamentally navigation. Only the selected
 * module fetches, instead of all seven racing on first paint. And each tab is a
 * real URL, so an official can send a colleague the outbreak view directly.
 *
 * These are links, not ARIA tabs: `aria-current` is the correct affordance, and
 * a screen reader announces them as the navigation they actually are.
 */

export interface TabItem {
  key: string;
  label: string;
  count?: number;
}

export function TabNav({
  items,
  active,
  basePath,
  paramName = "module",
  extraParams,
}: {
  items: TabItem[];
  active: string;
  basePath: string;
  paramName?: string;
  extraParams?: Record<string, string | undefined>;
}) {
  const href = (key: string) => {
    const query = new URLSearchParams();
    for (const [name, value] of Object.entries(extraParams ?? {})) {
      if (value) query.set(name, value);
    }
    query.set(paramName, key);
    return `${basePath}?${query.toString()}`;
  };

  return (
    <nav aria-label="Intelligence modules" className="w-full overflow-x-auto">
      <ul className="flex min-w-max items-center gap-1 border-b border-border">
        {items.map((item) => {
          const selected = item.key === active;
          return (
            <li key={item.key}>
              <Link
                href={href(item.key)}
                aria-current={selected ? "page" : undefined}
                className={cn(
                  "-mb-px flex items-center gap-1.5 whitespace-nowrap border-b-2 px-3 py-2",
                  "text-sm transition-colors duration-150",
                  selected
                    ? "border-primary font-medium text-foreground"
                    : "border-transparent text-muted-foreground hover:text-foreground",
                )}
              >
                {item.label}
                {item.count !== undefined && item.count > 0 ? (
                  <span
                    className={cn(
                      "rounded-full px-1.5 font-mono text-xs tabular-nums",
                      selected ? "bg-primary-muted text-primary" : "bg-neutral-muted",
                    )}
                  >
                    {item.count}
                  </span>
                ) : null}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
