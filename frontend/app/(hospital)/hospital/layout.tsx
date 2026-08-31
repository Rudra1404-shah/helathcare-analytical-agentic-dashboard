import { AppShell, type NavSection } from "@/components/shell/app-shell";
import { requireSession, resolveHospital } from "@/lib/session";

/**
 * The ten operational modules from PROJECT_SPEC section 2B, in the order a
 * shift actually uses them: capacity first, then the people, then the
 * patients, then what it costs.
 */
const SECTIONS: NavSection[] = [
  {
    heading: "Capacity",
    items: [
      { href: "/hospital", label: "Live overview", icon: "dashboard", exact: true },
      { href: "/hospital/analytics", label: "AI Intelligence Hub", icon: "analytics" },
      { href: "/hospital/inventory", label: "Inventory", icon: "inventory" },
      { href: "/hospital/profile", label: "Profile and beds", icon: "building" },
    ],
  },
  {
    heading: "Workforce",
    items: [
      { href: "/hospital/departments", label: "Departments", icon: "bed" },
      { href: "/hospital/doctors", label: "Doctors", icon: "doctors" },
      { href: "/hospital/staff", label: "Staff roster", icon: "staff" },
    ],
  },
  {
    heading: "Clinical",
    items: [
      { href: "/hospital/patients", label: "Patients", icon: "patients" },
      { href: "/hospital/cases", label: "Cases and triage", icon: "activity" },
      { href: "/hospital/case-types", label: "Case types", icon: "clipboard" },
    ],
  },
  {
    heading: "Finance",
    items: [{ href: "/hospital/bills", label: "Billing", icon: "receipt" }],
  },
];

export default async function HospitalLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const user = await requireSession();
  const { hospital } = await resolveHospital(user);

  return (
    <AppShell
      portal="Hospital operations"
      contextLabel={hospital ? `${hospital.name} · ${hospital.city}` : undefined}
      sections={SECTIONS}
      user={user}
    >
      {children}
    </AppShell>
  );
}
