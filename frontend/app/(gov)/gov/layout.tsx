import { AppShell, type NavSection } from "@/components/shell/app-shell";
import { requireSession } from "@/lib/session";

const SECTIONS: NavSection[] = [
  {
    heading: "Intelligence",
    items: [
      { href: "/gov/analytics", label: "AI Intelligence Hub", icon: "analytics" },
    ],
  },
  {
    heading: "Oversight",
    items: [
      { href: "/gov/hospitals", label: "Hospital directory", icon: "building2" },
      { href: "/gov/complaints", label: "Complaints desk", icon: "warning" },
      { href: "/gov/zones", label: "Zones and areas", icon: "map" },
    ],
  },
];

export default async function GovernmentLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const user = await requireSession();

  return (
    <AppShell
      portal="Health Ministry"
      contextLabel="National oversight"
      sections={SECTIONS}
      user={user}
    >
      {children}
    </AppShell>
  );
}
