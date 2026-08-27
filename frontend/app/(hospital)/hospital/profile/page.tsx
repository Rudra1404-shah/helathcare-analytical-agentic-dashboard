import type { Metadata } from "next";

import { AccreditationBadge } from "@/components/ui/badge";
import { PageHeader, Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import { dateOnly, humanise, quantity } from "@/lib/format";
import { withHospital } from "@/lib/hospital-page";
import type { Hospital } from "@/lib/types";

export const metadata: Metadata = { title: "Profile and beds" };

export default async function ProfilePage() {
  return withHospital("Profile and beds", (hospital) => (
    <>
      <PageHeader
        title="Profile and beds"
        description="The sanctioned capacity and licence details on record with the Health Ministry. Accreditation and licence number are the ministry's to change; a hospital maintains its own infrastructure figures."
        action={<AccreditationBadge status={hospital.accreditation_status} />}
      />

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel>
          <PanelHeader
            title="Sanctioned capacity"
            description="ICU and emergency beds are subsets of the sanctioned total, so their sum can never exceed it."
          />
          <PanelBody>
            <dl className="divide-y divide-border">
              <Metric
                label="Total sanctioned beds"
                value={String(hospital.capacity.total_sanctioned_beds)}
              />
              <Metric label="ICU beds" value={String(hospital.capacity.icu_beds)} />
              <Metric
                label="Emergency beds"
                value={String(hospital.capacity.emergency_beds)}
              />
              <Metric label="Ventilators" value={String(hospital.capacity.ventilators)} />
              <Metric
                label="Bulk oxygen capacity"
                value={quantity(hospital.capacity.oxygen_bulk_capacity_liters, "litres")}
              />
              <Metric label="Ambulances" value={String(hospital.capacity.ambulance_count)} />
            </dl>
          </PanelBody>
        </Panel>

        <div className="flex flex-col gap-4">
          <Panel>
            <PanelHeader title="Registration" />
            <PanelBody>
              <dl className="divide-y divide-border">
                <Detail label="Registered name" value={hospital.name} />
                <Detail label="Licence number" value={hospital.license_no} mono />
                <Detail label="Sector" value={humanise(hospital.sector_type)} />
                <Detail
                  label="Accreditation granted"
                  value={hospital.accredited_on ? dateOnly(hospital.accredited_on) : "Not granted"}
                />
                <Detail
                  label="Licence valid until"
                  value={
                    hospital.license_valid_until
                      ? dateOnly(hospital.license_valid_until)
                      : "Not recorded"
                  }
                />
                <Detail
                  label="Nodal officer"
                  value={hospital.nodal_officer_name ?? "Not assigned"}
                />
              </dl>
            </PanelBody>
          </Panel>

          <Panel>
            <PanelHeader title="Location and contact" />
            <PanelBody>
              <dl className="divide-y divide-border">
                <Detail label="City" value={`${hospital.city}, ${hospital.state}`} />
                <Detail label="Zone" value={hospital.zone_code} mono />
                <Detail label="Ward or area" value={hospital.ward_area ?? "Not recorded"} />
                <Detail label="Telephone" value={hospital.contact_phone ?? "Not recorded"} />
                <Detail label="Email" value={hospital.contact_email ?? "Not recorded"} />
              </dl>
            </PanelBody>
          </Panel>
        </div>
      </div>
    </>
  ));
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-4 py-2.5 first:pt-0 last:pb-0">
      <dt className="text-sm text-muted-foreground">{label}</dt>
      <dd className="font-mono text-lg font-semibold tabular-nums text-foreground">
        {value}
      </dd>
    </div>
  );
}

function Detail({
  label,
  value,
  mono,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="flex items-baseline justify-between gap-4 py-2.5 first:pt-0 last:pb-0">
      <dt className="text-sm text-muted-foreground">{label}</dt>
      <dd
        className={
          mono
            ? "text-right font-mono text-sm text-foreground"
            : "text-right text-sm text-foreground"
        }
      >
        {value}
      </dd>
    </div>
  );
}

export type { Hospital };
