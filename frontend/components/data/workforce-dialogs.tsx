"use client";

import { Building2, Plus, Stethoscope, UserPlus } from "lucide-react";
import { useState } from "react";

import {
  createDepartment,
  intakeStaff,
  onboardDoctor,
} from "@/app/(hospital)/hospital/actions";
import { Button } from "@/components/ui/button";
import { FormDialog } from "@/components/ui/dialog";
import { Field, Input, Select } from "@/components/ui/field";
import { useToast } from "@/components/ui/toast";
import { humanise } from "@/lib/format";
import type {
  AdminSupportStaffRole,
  Department,
  Doctor,
  EmploymentType,
  MedicalStaffRole,
  ShiftType,
  StaffRole,
} from "@/lib/types";

/**
 * Directory write flows: doctors, staff, and departments.
 *
 * The staff form branches on role because the platform does: clinical staff
 * carry a council registration and can be put on call, support staff cannot,
 * and the two post to different endpoints.
 */

const SHIFTS: ShiftType[] = ["MORNING", "EVENING", "NIGHT", "GENERAL"];

const EMPLOYMENT: EmploymentType[] = ["FULL_TIME", "VISITING", "ON_CALL"];

const MEDICAL_ROLES: MedicalStaffRole[] = [
  "STAFF_NURSE",
  "MATRON",
  "LAB_ASSISTANT",
  "WARD_BOY",
  "COMPOUNDER",
];

const SUPPORT_ROLES: AdminSupportStaffRole[] = [
  "DESK_ADMIN",
  "ADMIN",
  "ACCOUNTANT",
  "CLEANER",
  "SECURITY",
  "DRIVER",
  "LIFTMAN",
  "HELPER",
];

const NUMERIC = "font-mono tabular-nums";

/** A checkbox that reads as one at this density: hairline box, no custom control. */
function CheckboxField({
  id,
  name,
  label,
  hint,
  disabled,
  defaultChecked,
}: {
  id: string;
  name: string;
  label: string;
  hint?: string;
  disabled?: boolean;
  defaultChecked?: boolean;
}) {
  return (
    <label htmlFor={id} className="flex cursor-pointer items-start gap-2.5">
      <input
        id={id}
        name={name}
        type="checkbox"
        defaultChecked={defaultChecked}
        disabled={disabled}
        className="mt-0.5 size-4 shrink-0 rounded-[3px] border border-border accent-[var(--primary)]"
      />
      <span className="min-w-0">
        <span className="block text-sm text-foreground">{label}</span>
        {hint ? <span className="block text-xs text-muted-foreground">{hint}</span> : null}
      </span>
    </label>
  );
}

// --------------------------------------------------------------------------
// Doctors
// --------------------------------------------------------------------------

export function OnboardDoctorDialog({
  hospitalId,
  departments,
}: {
  hospitalId: string;
  departments: Department[];
}) {
  const { confirm } = useToast();

  if (departments.length === 0) {
    return (
      <Button size="sm" disabled title="Create a department before onboarding a doctor.">
        <Plus strokeWidth={1.75} aria-hidden="true" />
        Onboard doctor
      </Button>
    );
  }

  return (
    <FormDialog
      size="lg"
      trigger={
        <Button size="sm">
          <Stethoscope strokeWidth={1.75} aria-hidden="true" />
          Onboard doctor
        </Button>
      }
      title="Onboard a doctor"
      description="The licence number is checked against the medical council register."
      submitLabel="Onboard doctor"
      pendingLabel="Onboarding"
      action={(formData) => onboardDoctor(hospitalId, formData)}
      onSuccess={() => confirm("Doctor onboarded.")}
    >
      {({ pending }) => (
        <>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Full name" htmlFor="full_name" required>
              <Input
                id="full_name"
                name="full_name"
                required
                disabled={pending}
                placeholder="Dr Meera Iyer"
              />
            </Field>

            <Field label="Licence number" htmlFor="license_no" required>
              <Input
                id="license_no"
                name="license_no"
                required
                className="font-mono"
                disabled={pending}
                placeholder="MCI-2041-88213"
              />
            </Field>

            <Field label="Department" htmlFor="department_id" required>
              <Select id="department_id" name="department_id" required disabled={pending}>
                {departments.map((department) => (
                  <option key={department._id} value={department._id}>
                    {department.name}
                  </option>
                ))}
              </Select>
            </Field>

            <Field label="Specialisation" htmlFor="specialization" required>
              <Input
                id="specialization"
                name="specialization"
                required
                disabled={pending}
                placeholder="Cardiology"
              />
            </Field>

            <Field label="Qualification" htmlFor="qualification" required>
              <Input
                id="qualification"
                name="qualification"
                required
                disabled={pending}
                placeholder="MBBS, MD (Medicine)"
              />
            </Field>

            <Field label="Employment" htmlFor="employment_type" required>
              <Select
                id="employment_type"
                name="employment_type"
                defaultValue="FULL_TIME"
                disabled={pending}
              >
                {EMPLOYMENT.map((option) => (
                  <option key={option} value={option}>
                    {humanise(option)}
                  </option>
                ))}
              </Select>
            </Field>

            <Field label="Phone" htmlFor="phone" hint="Optional.">
              <Input
                id="phone"
                name="phone"
                type="tel"
                className="font-mono"
                disabled={pending}
                placeholder="+919820000000"
              />
            </Field>

            <Field label="Email" htmlFor="email" hint="Optional.">
              <Input id="email" name="email" type="email" disabled={pending} />
            </Field>

            <Field
              label="Daily patient limit"
              htmlFor="max_daily_patients"
              hint="Caps the rota."
              required
            >
              <Input
                id="max_daily_patients"
                name="max_daily_patients"
                type="number"
                min={1}
                max={200}
                inputMode="numeric"
                required
                defaultValue={30}
                className={NUMERIC}
                disabled={pending}
              />
            </Field>
          </div>

          <fieldset className="rounded-md border border-border p-3">
            <legend className="px-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Shifts
            </legend>
            <p className="mb-3 text-xs text-muted-foreground">
              At least one. A doctor on no shift can never be put on a rota.
            </p>
            <div className="grid grid-cols-2 gap-2">
              {SHIFTS.map((shift) => (
                <CheckboxField
                  key={shift}
                  id={"shift-" + shift}
                  name="shifts"
                  label={humanise(shift)}
                  disabled={pending}
                  defaultChecked={shift === "MORNING"}
                />
              ))}
            </div>
          </fieldset>

          <CheckboxField
            id="is_emergency_on_call"
            name="is_emergency_on_call"
            label="Available for emergency call"
            hint="Appears on the emergency rota outside their shift."
            disabled={pending}
          />
        </>
      )}
    </FormDialog>
  );
}

// --------------------------------------------------------------------------
// Staff
// --------------------------------------------------------------------------

export function IntakeStaffDialog({
  hospitalId,
  departments,
}: {
  hospitalId: string;
  departments: Department[];
}) {
  const { confirm } = useToast();
  const [role, setRole] = useState<StaffRole>("STAFF_NURSE");
  const clinical = (MEDICAL_ROLES as StaffRole[]).includes(role);

  return (
    <FormDialog
      size="lg"
      trigger={
        <Button size="sm">
          <UserPlus strokeWidth={1.75} aria-hidden="true" />
          Add staff member
        </Button>
      }
      title="Register a staff member"
      description="Clinical roles carry a council registration; support roles do not."
      submitLabel="Register staff member"
      pendingLabel="Registering"
      action={(formData) => intakeStaff(hospitalId, formData)}
      onSuccess={() => confirm("Staff member registered.")}
    >
      {({ pending }) => (
        <>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Full name" htmlFor="full_name" required>
              <Input
                id="full_name"
                name="full_name"
                required
                disabled={pending}
                placeholder="Kavita Patil"
              />
            </Field>

            <Field label="Employee ID" htmlFor="employee_id" required>
              <Input
                id="employee_id"
                name="employee_id"
                required
                maxLength={40}
                className="font-mono"
                disabled={pending}
                placeholder="EMP-0-014"
              />
            </Field>

            <Field label="Role" htmlFor="role" required>
              <Select
                id="role"
                name="role"
                value={role}
                onChange={(event) => setRole(event.target.value as StaffRole)}
                disabled={pending}
              >
                <optgroup label="Clinical">
                  {MEDICAL_ROLES.map((option) => (
                    <option key={option} value={option}>
                      {humanise(option)}
                    </option>
                  ))}
                </optgroup>
                <optgroup label="Admin and support">
                  {SUPPORT_ROLES.map((option) => (
                    <option key={option} value={option}>
                      {humanise(option)}
                    </option>
                  ))}
                </optgroup>
              </Select>
            </Field>

            <Field label="Shift" htmlFor="shift" required>
              <Select id="shift" name="shift" defaultValue="GENERAL" disabled={pending}>
                {SHIFTS.map((option) => (
                  <option key={option} value={option}>
                    {humanise(option)}
                  </option>
                ))}
              </Select>
            </Field>

            <Field label="Phone" htmlFor="phone" required>
              <Input
                id="phone"
                name="phone"
                type="tel"
                required
                className="font-mono"
                disabled={pending}
                placeholder="+919820000000"
              />
            </Field>

            <Field label="Department" htmlFor="department_id" hint="Optional.">
              <Select id="department_id" name="department_id" disabled={pending}>
                <option value="">Not assigned</option>
                {departments.map((department) => (
                  <option key={department._id} value={department._id}>
                    {department.name}
                  </option>
                ))}
              </Select>
            </Field>

            {clinical ? (
              <Field
                label="Council registration"
                htmlFor="registration_no"
                hint="Ties this person to a regulator."
                required
              >
                <Input
                  id="registration_no"
                  name="registration_no"
                  required
                  className="font-mono"
                  disabled={pending}
                  placeholder="MNC-48210"
                />
              </Field>
            ) : null}

            <Field label="Ward or area" htmlFor="assigned_ward_area" hint="Optional.">
              <Input
                id="assigned_ward_area"
                name="assigned_ward_area"
                disabled={pending}
                placeholder="East wing, floor 2"
              />
            </Field>
          </div>

          {clinical ? (
            <CheckboxField
              id="is_emergency_on_call"
              name="is_emergency_on_call"
              label="Available for emergency call"
              disabled={pending}
            />
          ) : null}
        </>
      )}
    </FormDialog>
  );
}

// --------------------------------------------------------------------------
// Departments
// --------------------------------------------------------------------------

export function CreateDepartmentDialog({
  hospitalId,
  doctors,
}: {
  hospitalId: string;
  doctors: Doctor[];
}) {
  const { confirm } = useToast();

  return (
    <FormDialog
      trigger={
        <Button size="sm">
          <Building2 strokeWidth={1.75} aria-hidden="true" />
          Create department
        </Button>
      }
      title="Create a department"
      description="The code is unique within this hospital and appears on every case."
      submitLabel="Create department"
      pendingLabel="Creating"
      action={(formData) => createDepartment(hospitalId, formData)}
      onSuccess={() => confirm("Department created.")}
    >
      {({ pending }) => (
        <>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Name" htmlFor="name" required>
              <Input
                id="name"
                name="name"
                required
                disabled={pending}
                placeholder="Cardiology"
              />
            </Field>

            <Field label="Code" htmlFor="code" hint="Two to twenty characters." required>
              <Input
                id="code"
                name="code"
                required
                minLength={2}
                maxLength={20}
                className="font-mono uppercase"
                disabled={pending}
                placeholder="CARD"
              />
            </Field>

            <Field label="Floor" htmlFor="floor" hint="Optional.">
              <Input
                id="floor"
                name="floor"
                maxLength={30}
                className={NUMERIC}
                disabled={pending}
                placeholder="2"
              />
            </Field>

            <Field label="Wing" htmlFor="wing" hint="Optional.">
              <Input
                id="wing"
                name="wing"
                maxLength={50}
                disabled={pending}
                placeholder="East"
              />
            </Field>

            <Field label="Beds" htmlFor="bed_count" hint="Sanctioned for this department.">
              <Input
                id="bed_count"
                name="bed_count"
                type="number"
                min={0}
                inputMode="numeric"
                defaultValue={0}
                className={NUMERIC}
                disabled={pending}
              />
            </Field>

            <Field label="Head of department" htmlFor="hod_doctor_id" hint="Optional.">
              <Select id="hod_doctor_id" name="hod_doctor_id" disabled={pending}>
                <option value="">Not assigned</option>
                {doctors.map((doctor) => (
                  <option key={doctor._id} value={doctor._id}>
                    {doctor.full_name}
                  </option>
                ))}
              </Select>
            </Field>
          </div>
        </>
      )}
    </FormDialog>
  );
}
