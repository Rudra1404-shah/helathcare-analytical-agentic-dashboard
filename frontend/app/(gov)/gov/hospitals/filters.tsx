import { Search } from "lucide-react";

import { Button } from "@/components/ui/button";
import { FilterSelect, Input } from "@/components/ui/field";
import { Panel } from "@/components/ui/panel";
import { apiTry } from "@/lib/api";
import type { AccreditationStatus, SectorType } from "@/lib/types";

const SECTORS: SectorType[] = ["PUBLIC", "PRIVATE", "TRUST"];
const ACCREDITATIONS: AccreditationStatus[] = [
  "NABH",
  "STATE_LICENSED",
  "PENDING",
  "BLACKLISTED",
];

const ACCREDITATION_LABEL: Record<AccreditationStatus, string> = {
  NABH: "NABH accredited",
  STATE_LICENSED: "State licensed",
  PENDING: "Pending",
  BLACKLISTED: "Blacklisted",
};

/**
 * A plain GET form. Filters live in the URL, so a ministry official can
 * bookmark "blacklisted hospitals in Mumbai" and share the link, and the back
 * button behaves the way they expect.
 */
export async function AccreditationFilters({
  current,
}: {
  current: { city?: string; sector_type?: string; accreditation_status?: string; search?: string };
}) {
  const cities = await apiTry<{ state: string; city: string }[]>("/hospitals/cities");
  const options = cities.ok ? cities.data : [];

  return (
    <Panel className="p-3">
      <form className="flex flex-wrap items-end gap-3" role="search">
        <div className="flex min-w-56 flex-1 flex-col gap-1">
          <label
            htmlFor="search"
            className="text-xs font-medium text-muted-foreground"
          >
            Name or licence number
          </label>
          <div className="relative">
            <Search
              className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
              strokeWidth={1.75}
              aria-hidden="true"
            />
            <Input
              id="search"
              name="search"
              type="search"
              defaultValue={current.search ?? ""}
              className="h-8 pl-8"
              placeholder="Sunrise, MH-HOSP-10021"
            />
          </div>
        </div>

        <FilterSelect label="City" name="city" defaultValue={current.city ?? ""}>
          <option value="">All cities</option>
          {options.map((option) => (
            <option key={`${option.state}-${option.city}`} value={option.city}>
              {option.city}, {option.state}
            </option>
          ))}
        </FilterSelect>

        <FilterSelect
          label="Sector"
          name="sector_type"
          defaultValue={current.sector_type ?? ""}
        >
          <option value="">All sectors</option>
          {SECTORS.map((sector) => (
            <option key={sector} value={sector}>
              {sector.charAt(0) + sector.slice(1).toLowerCase()}
            </option>
          ))}
        </FilterSelect>

        <FilterSelect
          label="Accreditation"
          name="accreditation_status"
          defaultValue={current.accreditation_status ?? ""}
        >
          <option value="">Any status</option>
          {ACCREDITATIONS.map((status) => (
            <option key={status} value={status}>
              {ACCREDITATION_LABEL[status]}
            </option>
          ))}
        </FilterSelect>

        <div className="flex items-center gap-2">
          <Button type="submit" size="sm">
            Apply
          </Button>
          <Button type="submit" variant="ghost" size="sm" name="reset" value="1" formAction="/gov/hospitals">
            Clear
          </Button>
        </div>
      </form>
    </Panel>
  );
}
