import {
  Activity,
  Bed,
  Building,
  Building2,
  ClipboardList,
  FileHeart,
  LayoutDashboard,
  Map,
  MessageSquareWarning,
  Package,
  Receipt,
  ShieldPlus,
  Stethoscope,
  UserRound,
  Users,
  type LucideIcon,
} from "lucide-react";

/**
 * Navigation icons, addressed by name.
 *
 * A component reference cannot cross the server-to-client boundary: React
 * refuses to serialise a function, and the sidebar is a Client Component
 * because it needs the current path. Server layouts therefore name their icon
 * and the client resolves it here.
 */
export const NAV_ICONS = {
  activity: Activity,
  bed: Bed,
  building: Building,
  building2: Building2,
  clipboard: ClipboardList,
  dashboard: LayoutDashboard,
  doctors: Stethoscope,
  healthRecord: FileHeart,
  inventory: Package,
  map: Map,
  patients: UserRound,
  receipt: Receipt,
  shield: ShieldPlus,
  staff: Users,
  warning: MessageSquareWarning,
} as const satisfies Record<string, LucideIcon>;

export type NavIconName = keyof typeof NAV_ICONS;
