import { AlertTriangle, Package } from "lucide-react";
import type { Metadata } from "next";
import { Suspense } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { FilterSelect } from "@/components/ui/field";
import { PageHeader, Panel, PanelHeader } from "@/components/ui/panel";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/ui/states";
import { Table, TBody, TD, TDMeta, TDPrimary, TH, THead, TR, TableWrap } from "@/components/ui/table";
import { apiTry } from "@/lib/api";
import { dateOnly, humanise, quantity, relative } from "@/lib/format";
import { withHospital } from "@/lib/hospital-page";
import type { InventoryCategory, InventoryItem, Paginated } from "@/lib/types";

export const metadata: Metadata = { title: "Inventory" };

const CATEGORIES: InventoryCategory[] = [
  "GENERAL_BEDS",
  "ICU_BEDS",
  "VENTILATORS",
  "OXYGEN_CYLINDERS",
  "OXYGEN_LITERS",
  "MEDICINES",
  "CONSUMABLES",
];

interface Filters {
  category?: InventoryCategory;
  below_threshold?: string;
}

export default async function InventoryPage({
  searchParams,
}: {
  searchParams: Promise<Filters>;
}) {
  const filters = await searchParams;

  return withHospital("Inventory", (hospital) => (
    <>
      <PageHeader
        title="Inventory"
        description="Beds, ventilators, oxygen, medicines, and consumables. Available stock moves automatically as cases are admitted and discharged, so a bed can never be occupied by a patient the register says is free."
      />

      <Panel className="p-3">
        <form className="flex flex-wrap items-end gap-3">
          <FilterSelect
            label="Category"
            name="category"
            defaultValue={filters.category ?? ""}
          >
            <option value="">All categories</option>
            {CATEGORIES.map((category) => (
              <option key={category} value={category}>
                {humanise(category)}
              </option>
            ))}
          </FilterSelect>

          <FilterSelect
            label="Stock level"
            name="below_threshold"
            defaultValue={filters.below_threshold ?? ""}
          >
            <option value="">Everything</option>
            <option value="true">At or below threshold</option>
            <option value="false">Above threshold</option>
          </FilterSelect>

          <Button type="submit" size="sm">
            Apply
          </Button>
        </form>
      </Panel>

      <Panel className="mt-4">
        <Suspense
          key={JSON.stringify(filters)}
          fallback={
            <>
              <PanelHeader title="Stock register" description="Loading" />
              <TableSkeleton rows={8} columns={6} />
            </>
          }
        >
          <StockTable hospitalId={hospital._id} filters={filters} />
        </Suspense>
      </Panel>
    </>
  ));
}

async function StockTable({
  hospitalId,
  filters,
}: {
  hospitalId: string;
  filters: Filters;
}) {
  const result = await apiTry<Paginated<InventoryItem>>(
    `/hospitals/${hospitalId}/inventory`,
    {
      query: {
        category: filters.category,
        below_threshold:
          filters.below_threshold === "" || filters.below_threshold === undefined
            ? undefined
            : filters.below_threshold === "true",
        limit: 200,
      },
    },
  );

  if (!result.ok) {
    return (
      <>
        <PanelHeader title="Stock register" />
        <ErrorState message={result.error} />
      </>
    );
  }

  const { items, meta } = result.data;

  if (items.length === 0) {
    return (
      <>
        <PanelHeader title="Stock register" />
        <EmptyState
          icon={Package}
          title="Nothing matches these filters"
          description="Add a stock line so this hospital's capacity appears on the live overview and in the ministry's national resource view."
        />
      </>
    );
  }

  const lowCount = items.filter(
    (item) => item.available_stock <= item.min_safety_threshold,
  ).length;

  return (
    <>
      <PanelHeader
        title="Stock register"
        description={
          lowCount > 0
            ? `${meta.total} tracked, ${lowCount} at or below the safety threshold`
            : `${meta.total} tracked, all above threshold`
        }
      />
      <TableWrap>
        <Table>
          <THead>
            <tr>
              <TH>Item</TH>
              <TH>Category</TH>
              <TH numeric>Available</TH>
              <TH numeric>Total</TH>
              <TH numeric>Threshold</TH>
              <TH>Last restocked</TH>
              <TH>Expiry</TH>
            </tr>
          </THead>
          <TBody>
            {items.map((item) => {
              const low = item.available_stock <= item.min_safety_threshold;
              return (
                <TR key={item._id}>
                  <TDPrimary>
                    <span className="flex items-center gap-1.5">
                      {low ? (
                        <AlertTriangle
                          className="size-3.5 shrink-0 text-critical"
                          strokeWidth={1.75}
                          aria-hidden="true"
                        />
                      ) : null}
                      {item.item_name}
                    </span>
                    {low ? (
                      <TDMeta>
                        <Badge tone="critical">Below safety threshold</Badge>
                      </TDMeta>
                    ) : null}
                  </TDPrimary>
                  <TD>{humanise(item.category)}</TD>
                  <TD numeric className={low ? "text-critical" : undefined}>
                    {quantity(item.available_stock)}
                  </TD>
                  <TD numeric>{quantity(item.total_stock, item.unit)}</TD>
                  <TD numeric>{quantity(item.min_safety_threshold)}</TD>
                  <TD>{item.last_restocked_at ? relative(item.last_restocked_at) : "Not recorded"}</TD>
                  <TD>{item.expires_on ? dateOnly(item.expires_on) : "Not applicable"}</TD>
                </TR>
              );
            })}
          </TBody>
        </Table>
      </TableWrap>
    </>
  );
}
