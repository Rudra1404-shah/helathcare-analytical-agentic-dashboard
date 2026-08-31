import {
  CreateDepartmentDialog,
  IntakeStaffDialog,
  OnboardDoctorDialog,
} from "@/components/data/workforce-dialogs";
import { apiTry } from "@/lib/api";
import type { Department, Doctor, Paginated } from "@/lib/types";

/**
 * Server-side loaders for the directory dialogs.
 *
 * Each dialog needs one list to populate a selector. Fetching it here keeps the
 * dialog itself a pure client component with no data dependency of its own, and
 * lets the page stream the rest of the view without waiting on the selector.
 *
 * A failed lookup yields an empty list rather than an error page: the dialog
 * renders its own disabled state and says what is missing.
 */

async function departmentsOf(hospitalId: string): Promise<Department[]> {
  const result = await apiTry<Paginated<Department>>(
    `/hospitals/${hospitalId}/departments`,
    { query: { limit: 100 } },
  );
  return result.ok ? result.data.items : [];
}

async function doctorsOf(hospitalId: string): Promise<Doctor[]> {
  const result = await apiTry<Paginated<Doctor>>(`/hospitals/${hospitalId}/doctors`, {
    query: { limit: 200 },
  });
  return result.ok ? result.data.items : [];
}

export async function DoctorIntakeTrigger({ hospitalId }: { hospitalId: string }) {
  return (
    <OnboardDoctorDialog hospitalId={hospitalId} departments={await departmentsOf(hospitalId)} />
  );
}

export async function StaffIntakeTrigger({ hospitalId }: { hospitalId: string }) {
  return (
    <IntakeStaffDialog hospitalId={hospitalId} departments={await departmentsOf(hospitalId)} />
  );
}

export async function DepartmentCreateTrigger({ hospitalId }: { hospitalId: string }) {
  return <CreateDepartmentDialog hospitalId={hospitalId} doctors={await doctorsOf(hospitalId)} />;
}
