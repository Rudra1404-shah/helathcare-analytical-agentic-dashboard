import { Building2 } from "lucide-react";
import type { Metadata } from "next";
import { Suspense } from "react";

import { AccreditationFilters } from "@/app/(gov)/gov/hospitals/filters";
import { HospitalRow } from "@/app/(gov)/gov/hospitals/hospital-row";
import { Panel, PageHeader, PanelHeader } from "@/components/ui/panel";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/ui/states";
import {
  Table,
  TBody,
  TD,
  TH,
  THead,
  TableWrap,
} from "@/components/ui/table";
import { apiTry } from "@/lib/api";
import type {
  AccreditationStatus,
  Hospital,
  Paginated,
  SectorType,
} from "@/lib/types";

export const metadata: Metadata = { title: "Hospital directory" };

interface Filters {
  city?: string;
  sector_type?: SectorType;
  accreditation_status?: AccreditationStatus;
  search?: string;
  page?: string;
}

export default async function HospitalDirectoryPage({
  searchParams,
}: {
  searchParams: Promise<Filters>;
}) {
  const filters = await searchParams;

  return (
    <>
      <PageHeader
        title="Hospital directory"
        description="Every registered public, private, and trust hospital on the platform. Accreditation changes take effect immediately and are recorded against the ministry account that made them."
      />

      <Suspense fallback={<FilterFallback />}>
        <AccreditationFilters current={filters} />
      </Suspense>

      <Panel className="mt-4">
        <Suspense key={JSON.stringify(filters)} fallback={<DirectorySkeleton />}>
          <DirectoryTable filters={filters} />
        </Suspense>
      </Panel>
    </>
  );
}

function FilterFallback() {
  return <div className="skeleton h-14 rounded-lg" />;
}

function DirectorySkeleton() {
  return (
    <>
      <PanelHeader title="Registered hospitals" description="Loading" />
      <TableSkeleton rows={8} columns={6} />
    </>
  );
}

async function DirectoryTable({ filters }: { filters: Filters }) {
  const page = Number(filters.page ?? "1");
  const result = await apiTry<Paginated<Hospital>>("/hospitals", {
    query: {
      city: filters.city,
      sector_type: filters.sector_type,
      accreditation_status: filters.accreditation_status,
      search: filters.search,
      page: Number.isFinite(page) && page > 0 ? page : 1,
      limit: 50,
    },
  });

  if (!result.ok) {
    return (
      <>
        <PanelHeader title="Registered hospitals" />
        <ErrorState message={result.error} />
      </>
    );
  }

  const { items, meta } = result.data;

  if (items.length === 0) {
    return (
      <>
        <PanelHeader title="Registered hospitals" />
        <EmptyState
          icon={Building2}
          title="No hospitals match these filters"
          description="Clear the filters to see the full register, or register a hospital through the Verification and Accreditation form."
        />
      </>
    );
  }

  return (
    <>
      <PanelHeader
        title="Registered hospitals"
        description={`${meta.total} on the register, showing ${items.length}`}
      />
      <TableWrap>
        <Table>
          <THead>
            <tr>
              <TH>Hospital</TH>
              <TH>Location</TH>
              <TH>Sector</TH>
              <TH numeric>Beds</TH>
              <TH numeric>ICU</TH>
              <TH>Accreditation</TH>
              <TH className="text-right">Action</TH>
            </tr>
          </THead>
          <TBody>
            {items.map((hospital) => (
              <HospitalRow key={hospital._id} hospital={hospital} />
            ))}
          </TBody>
        </Table>
      </TableWrap>
      {meta.total > items.length ? (
        <div className="border-t border-border px-4 py-2.5">
          <TD className="p-0 text-xs text-muted-foreground">
            Page {meta.page} of {Math.ceil(meta.total / meta.limit)}
          </TD>
        </div>
      ) : null}
    </>
  );
}
