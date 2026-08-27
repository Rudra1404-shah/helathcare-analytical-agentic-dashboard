import { MessageSquareWarning } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { EvidenceGallery } from "@/components/data/evidence";
import { InvestigationBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { PageHeader, Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/states";
import { apiTry } from "@/lib/api";
import { dateTime, humanise } from "@/lib/format";
import type { Complaint, Hospital, Paginated } from "@/lib/types";

export const metadata: Metadata = { title: "Your complaints" };

export default function CitizenComplaintsPage() {
  return (
    <>
      <PageHeader
        title="Your complaints"
        description="Everything you have filed, and where each one has reached. You see only your own complaints."
        action={
          <Button asChild size="sm">
            <Link href="/citizen/complaint">File a complaint</Link>
          </Button>
        }
      />
      <Suspense
        fallback={
          <div className="flex flex-col gap-4">
            <Skeleton className="h-40 rounded-lg" />
            <Skeleton className="h-40 rounded-lg" />
          </div>
        }
      >
        <ComplaintList />
      </Suspense>
    </>
  );
}

async function ComplaintList() {
  const [complaints, hospitals] = await Promise.all([
    apiTry<Paginated<Complaint>>("/complaints", { query: { limit: 50 } }),
    apiTry<Paginated<Hospital>>("/hospitals", { query: { limit: 200 } }),
  ]);

  if (!complaints.ok) {
    return (
      <Panel>
        <ErrorState message={complaints.error} />
      </Panel>
    );
  }

  const hospitalName = new Map(
    hospitals.ok ? hospitals.data.items.map((item) => [item._id, item.name]) : [],
  );

  if (complaints.data.items.length === 0) {
    return (
      <Panel>
        <EmptyState
          icon={MessageSquareWarning}
          title="You have not filed any complaints"
          description="If a hospital overcharged you, refused you a bed, or treated you poorly, report it with photographic or video evidence and the ministry will investigate."
          action={
            <Button asChild size="sm">
              <Link href="/citizen/complaint">File a complaint</Link>
            </Button>
          }
        />
      </Panel>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      {complaints.data.items.map((complaint) => (
        <Panel key={complaint._id}>
          <PanelHeader
            title={
              <span className="font-mono text-sm">{complaint.complaint_number}</span>
            }
            description={`${humanise(complaint.category)} against ${
              hospitalName.get(complaint.hospital_id) ?? "a registered hospital"
            } · incident ${dateTime(complaint.incident_at)}`}
            action={<InvestigationBadge status={complaint.investigation_status} />}
          />
          <PanelBody className="flex flex-col gap-4">
            <p className="max-w-[70ch] whitespace-pre-line text-sm leading-relaxed text-foreground">
              {complaint.description}
            </p>

            <div>
              <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Evidence you submitted
              </h3>
              <EvidenceGallery evidence={complaint.evidence} />
            </div>

            {complaint.closed_at ? (
              <div className="rounded-md bg-surface-muted px-3 py-2.5">
                <h3 className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  Outcome
                </h3>
                <p className="mt-1 text-sm font-medium text-foreground">
                  {complaint.action_taken
                    ? humanise(complaint.action_taken)
                    : humanise(complaint.investigation_status)}
                  <span className="ml-2 font-normal text-muted-foreground">
                    {dateTime(complaint.closed_at)}
                  </span>
                </p>
                {complaint.closure_remarks ? (
                  <p className="mt-1.5 max-w-[70ch] text-sm text-muted-foreground">
                    {complaint.closure_remarks}
                  </p>
                ) : null}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">
                Still under investigation. The outcome and the ministry&rsquo;s reasoning
                appear here once a decision is recorded.
              </p>
            )}
          </PanelBody>
        </Panel>
      ))}
    </div>
  );
}
