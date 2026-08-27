import type { Metadata } from "next";
import { Suspense } from "react";

import { ComplaintForm } from "@/app/(citizen)/citizen/complaint/complaint-form";
import { PageHeader, Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import { ErrorState, Skeleton } from "@/components/ui/states";
import { apiTry } from "@/lib/api";
import type { Hospital, Paginated } from "@/lib/types";

export const metadata: Metadata = { title: "File a complaint" };

export default function FileComplaintPage() {
  return (
    <>
      <PageHeader
        title="File a complaint"
        description="Report overcharging, refused admission, negligence, poor hygiene, or a shortage of supplies at a registered hospital. The Health Ministry investigates every complaint and records what it decided."
      />
      <Panel className="mx-auto max-w-2xl">
        <Suspense fallback={<FormSkeleton />}>
          <FormWithHospitals />
        </Suspense>
      </Panel>
    </>
  );
}

function FormSkeleton() {
  return (
    <>
      <PanelHeader title="File a complaint" description="Loading" />
      <PanelBody className="flex flex-col gap-4">
        <Skeleton className="h-16" />
        <Skeleton className="h-16" />
        <Skeleton className="h-32" />
        <Skeleton className="h-28" />
      </PanelBody>
    </>
  );
}

async function FormWithHospitals() {
  const result = await apiTry<Paginated<Hospital>>("/hospitals", {
    query: { limit: 200 },
  });

  if (!result.ok) {
    return <ErrorState message={result.error} />;
  }

  return <ComplaintForm hospitals={result.data.items} />;
}
