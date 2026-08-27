import { AppShell, type NavSection } from "@/components/shell/app-shell";
import { requireSession } from "@/lib/session";

const SECTIONS: NavSection[] = [
  {
    heading: "Your health",
    items: [
      { href: "/citizen/health-record", label: "Health record", icon: "healthRecord" },
    ],
  },
  {
    heading: "Grievances",
    items: [
      { href: "/citizen/complaint", label: "File a complaint", icon: "shield" },
      { href: "/citizen/complaints", label: "Your complaints", icon: "warning" },
    ],
  },
];

export default async function CitizenLayout({ children }: { children: React.ReactNode }) {
  const user = await requireSession();

  return (
    <AppShell
      portal="Citizen portal"
      contextLabel="Your unified health record"
      sections={SECTIONS}
      user={user}
    >
      {children}
    </AppShell>
  );
}
