import { Bed } from "lucide-react";
import type * as React from "react";

import { PageHeader, Panel } from "@/components/ui/panel";
import { EmptyState, ErrorState } from "@/components/ui/states";
import { requireSession, resolveHospital } from "@/lib/session";
import type { Hospital } from "@/lib/types";

/**
 * Every hospital view begins the same way: resolve which hospital this account
 * works at, and render a usable page when there is not one. Repeating that in
 * ten files would guarantee the tenth forgets the not-linked state.
 */
export async function withHospital(
  title: string,
  render: (hospital: Hospital) => React.ReactNode,
): Promise<React.ReactNode> {
  const user = await requireSession();
  const { hospital, error } = await resolveHospital(user);

  if (hospital) return render(hospital);

  return (
    <>
      <PageHeader title={title} />
      <Panel>
        {error ? (
          <ErrorState message={error} />
        ) : (
          <EmptyState
            icon={Bed}
            title="No hospital is linked to this account"
            description="A hospital account is scoped to the hospital that issued it. Ask the Health Ministry to register the hospital before using the operational modules."
          />
        )}
      </Panel>
    </>
  );
}
