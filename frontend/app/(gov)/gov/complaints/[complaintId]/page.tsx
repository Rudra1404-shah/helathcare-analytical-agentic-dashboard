import { ArrowLeft } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";

import { InvestigationForm } from "@/app/(gov)/gov/complaints/[complaintId]/investigation-form";
import { EvidenceGallery } from "@/components/data/evidence";
import { InvestigationBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { PageHeader, Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import { ErrorState } from "@/components/ui/states";
import { apiTry } from "@/lib/api";
import { dateTime, humanise } from "@/lib/format";
import type { Complaint, Hospital } from "@/lib/types";

export const metadata: Metadata = { title: "Investigation" };

export default async function InvestigationPage({
  params,
}: {
  params: Promise<{ complaintId: string }>;
}) {
  const { complaintId } = await params;
  const result = await apiTry<Complaint>(`/complaints/${complaintId}`);

  if (!result.ok) {
    return (
      <>
        <BackLink />
        <Panel className="mt-4">
          <ErrorState message={result.error} />
        </Panel>
      </>
    );
  }

  const complaint = result.data;
  const hospital = await apiTry<Hospital>(`/hospitals/${complaint.hospital_id}`);

  return (
    <>
      <BackLink />

      <PageHeader
        title={`Complaint ${complaint.complaint_number}`}
        description={`${humanise(complaint.category)} filed against ${
          hospital.ok ? hospital.data.name : "a registered hospital"
        }, incident on ${dateTime(complaint.incident_at)}.`}
        action={<InvestigationBadge status={complaint.investigation_status} />}
      />

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_24rem]">
        <div className="flex flex-col gap-4">
          <Panel>
            <PanelHeader
              title="The citizen's account"
              description={`Submitted ${dateTime(complaint.created_at)}`}
            />
            <PanelBody>
              <p className="max-w-[70ch] whitespace-pre-line text-sm leading-relaxed text-foreground">
                {complaint.description}
              </p>
            </PanelBody>
          </Panel>

          <Panel>
            <PanelHeader
              title="Evidence"
              description={`${complaint.evidence.length} attachment${
                complaint.evidence.length === 1 ? "" : "s"
              }. Mandatory to file, so every complaint here is substantiated.`}
            />
            <PanelBody>
              <EvidenceGallery evidence={complaint.evidence} />
            </PanelBody>
          </Panel>

          {complaint.hospital_explanation || complaint.closure_remarks ? (
            <Panel>
              <PanelHeader title="Investigation trail" />
              <PanelBody className="flex flex-col gap-4">
                {complaint.hospital_explanation ? (
                  <div>
                    <h3 className="text-sm font-medium text-foreground">
                      Hospital explanation
                    </h3>
                    <p className="mt-1 max-w-[70ch] text-sm text-muted-foreground">
                      {complaint.hospital_explanation}
                    </p>
                  </div>
                ) : null}
                {complaint.action_taken ? (
                  <div>
                    <h3 className="text-sm font-medium text-foreground">Action taken</h3>
                    <p className="mt-1 text-sm text-muted-foreground">
                      {humanise(complaint.action_taken)}
                      {complaint.closed_at ? ` on ${dateTime(complaint.closed_at)}` : ""}
                    </p>
                  </div>
                ) : null}
                {complaint.closure_remarks ? (
                  <div>
                    <h3 className="text-sm font-medium text-foreground">Closure remarks</h3>
                    <p className="mt-1 max-w-[70ch] text-sm text-muted-foreground">
                      {complaint.closure_remarks}
                    </p>
                  </div>
                ) : null}
              </PanelBody>
            </Panel>
          ) : null}
        </div>

        <Panel className="h-fit lg:sticky lg:top-24">
          <PanelHeader
            title="Resolution"
            description={
              complaint.closed_at
                ? "This investigation is closed and cannot be reopened."
                : "Closing requires a recorded action and the reasoning behind it."
            }
          />
          <PanelBody>
            <InvestigationForm complaint={complaint} />
          </PanelBody>
        </Panel>
      </div>
    </>
  );
}

function BackLink() {
  return (
    <Button asChild variant="ghost" size="sm" className="-ml-3 mb-1">
      <Link href="/gov/complaints">
        <ArrowLeft strokeWidth={1.75} aria-hidden="true" />
        Complaints desk
      </Link>
    </Button>
  );
}
