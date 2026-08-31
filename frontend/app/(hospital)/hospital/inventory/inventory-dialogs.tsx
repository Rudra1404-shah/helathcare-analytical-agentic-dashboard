"use client";

import { PackagePlus, Plus, SlidersHorizontal } from "lucide-react";
import { useState } from "react";

import {
  addInventoryItem,
  adjustStock,
  updateInventoryItem,
} from "@/app/(hospital)/hospital/actions";
import { Button } from "@/components/ui/button";
import { FormDialog } from "@/components/ui/dialog";
import { Field, Input, Select } from "@/components/ui/field";
import { useToast } from "@/components/ui/toast";
import { humanise } from "@/lib/format";
import type { InventoryCategory, InventoryItem, InventoryUnit } from "@/lib/types";

/**
 * Stock write flows.
 *
 * Restocking and re-thresholding are deliberately separate actions rather than
 * one compound dialog. They are two API calls, and a single form that half
 * succeeds would leave the ward unsure which half took effect.
 */

const CATEGORIES: InventoryCategory[] = [
  "GENERAL_BEDS",
  "ICU_BEDS",
  "VENTILATORS",
  "OXYGEN_CYLINDERS",
  "OXYGEN_LITERS",
  "MEDICINES",
  "CONSUMABLES",
];

const UNITS: InventoryUnit[] = [
  "UNITS",
  "LITERS",
  "PIECES",
  "BOXES",
  "VIALS",
  "STRIPS",
  "KG",
  "ML",
];

/** Categories that are physical capacity rather than consumable stock. */
const CAPACITY_CATEGORIES = new Set<InventoryCategory>([
  "GENERAL_BEDS",
  "ICU_BEDS",
  "VENTILATORS",
]);

const NUMERIC = "font-mono tabular-nums";

export function AddStockItemDialog({ hospitalId }: { hospitalId: string }) {
  const { confirm } = useToast();
  const [category, setCategory] = useState<InventoryCategory>("MEDICINES");
  const isCapacity = CAPACITY_CATEGORIES.has(category);

  return (
    <FormDialog
      size="lg"
      trigger={
        <Button size="sm">
          <Plus strokeWidth={1.75} aria-hidden="true" />
          Add stock item
        </Button>
      }
      title="Add a stock line"
      description="Capacity categories feed the public bed availability figures."
      submitLabel="Add item"
      pendingLabel="Adding"
      action={(formData) => addInventoryItem(hospitalId, formData)}
      onSuccess={() => confirm("Stock line added.")}
    >
      {({ pending }) => (
        <>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Item name" htmlFor="item_name" required>
              <Input
                id="item_name"
                name="item_name"
                required
                maxLength={120}
                disabled={pending}
                placeholder="Paracetamol 500mg"
              />
            </Field>

            <Field label="Category" htmlFor="category" required>
              <Select
                id="category"
                name="category"
                value={category}
                onChange={(event) => setCategory(event.target.value as InventoryCategory)}
                disabled={pending}
              >
                {CATEGORIES.map((option) => (
                  <option key={option} value={option}>
                    {humanise(option)}
                  </option>
                ))}
              </Select>
            </Field>

            <Field
              label="Total stock"
              htmlFor="total_stock"
              hint={isCapacity ? "Sanctioned count." : "Everything held."}
              required
            >
              <Input
                id="total_stock"
                name="total_stock"
                type="number"
                min={0}
                step="0.01"
                inputMode="decimal"
                required
                className={NUMERIC}
                disabled={pending}
                placeholder="4000"
              />
            </Field>

            <Field
              label="Available now"
              htmlFor="available_stock"
              hint={isCapacity ? "Not currently occupied." : "Not yet issued."}
              required
            >
              <Input
                id="available_stock"
                name="available_stock"
                type="number"
                min={0}
                step="0.01"
                inputMode="decimal"
                required
                className={NUMERIC}
                disabled={pending}
                placeholder="3200"
              />
            </Field>

            <Field label="Unit" htmlFor="unit" required>
              <Select
                id="unit"
                name="unit"
                defaultValue={isCapacity ? "UNITS" : "STRIPS"}
                disabled={pending}
              >
                {UNITS.map((option) => (
                  <option key={option} value={option}>
                    {humanise(option)}
                  </option>
                ))}
              </Select>
            </Field>

            <Field
              label="Safety threshold"
              htmlFor="min_safety_threshold"
              hint="Below this, the line is flagged."
              required
            >
              <Input
                id="min_safety_threshold"
                name="min_safety_threshold"
                type="number"
                min={0}
                step="0.01"
                inputMode="decimal"
                required
                defaultValue={0}
                className={NUMERIC}
                disabled={pending}
              />
            </Field>
          </div>

          <Field
            label="Expires on"
            htmlFor="expires_on"
            hint="Optional. Medicines and consumables only."
          >
            <Input
              id="expires_on"
              name="expires_on"
              type="date"
              className={NUMERIC}
              disabled={pending}
            />
          </Field>
        </>
      )}
    </FormDialog>
  );
}

export function RestockDialog({ item }: { item: InventoryItem }) {
  const { confirm } = useToast();
  const [direction, setDirection] = useState<"receive" | "consume">("receive");
  const removing = direction === "consume";

  return (
    <FormDialog
      trigger={
        <Button variant="ghost" size="sm">
          <PackagePlus strokeWidth={1.75} aria-hidden="true" />
          Restock
        </Button>
      }
      title="Adjust stock"
      description={item.item_name}
      submitLabel={removing ? "Record consumption" : "Record delivery"}
      submitVariant={removing ? "destructive" : "primary"}
      action={(formData) => adjustStock(item._id, formData)}
      onSuccess={() => confirm("Stock adjusted for " + item.item_name + ".")}
    >
      {({ pending }) => (
        <>
          <p className="rounded-md bg-surface-muted px-3 py-2 text-sm text-muted-foreground">
            Currently{" "}
            <span className="font-mono tabular-nums text-foreground">
              {item.available_stock}
            </span>{" "}
            of{" "}
            <span className="font-mono tabular-nums text-foreground">{item.total_stock}</span>{" "}
            {item.unit.toLowerCase()} free.
          </p>

          <p className="text-xs text-muted-foreground">
            {removing
              ? "Reduces available stock. The sanctioned total is unchanged."
              : "Raises both the total held and the amount free."}
          </p>

          {/* The action needs the figures this form was rendered against to
              raise the total on a delivery. */}
          <input type="hidden" name="current_total" value={item.total_stock} />
          <input type="hidden" name="current_available" value={item.available_stock} />

          <div className="grid grid-cols-2 gap-3">
            <Field label="Direction" htmlFor="direction" required>
              <Select
                id="direction"
                name="direction"
                value={direction}
                onChange={(event) =>
                  setDirection(event.target.value as "receive" | "consume")
                }
                disabled={pending}
              >
                <option value="receive">Delivery received</option>
                <option value="consume">Consumed or written off</option>
              </Select>
            </Field>

            <Field label="Quantity" htmlFor="quantity" required>
              <Input
                id="quantity"
                name="quantity"
                type="number"
                min={0}
                step="0.01"
                inputMode="decimal"
                required
                className={NUMERIC}
                disabled={pending}
                placeholder="500"
              />
            </Field>
          </div>

          <Field
            label="Reason"
            htmlFor="reason"
            hint="Recorded against your account in the stock ledger."
            required
          >
            <Input
              id="reason"
              name="reason"
              required
              maxLength={120}
              disabled={pending}
              placeholder={removing ? "Expired batch withdrawn" : "Quarterly delivery received"}
            />
          </Field>
        </>
      )}
    </FormDialog>
  );
}

export function EditThresholdDialog({ item }: { item: InventoryItem }) {
  const { confirm } = useToast();

  return (
    <FormDialog
      trigger={
        <Button variant="ghost" size="sm">
          <SlidersHorizontal strokeWidth={1.75} aria-hidden="true" />
          Thresholds
        </Button>
      }
      title="Edit thresholds"
      description={item.item_name}
      submitLabel="Save thresholds"
      action={(formData) => updateInventoryItem(item._id, formData)}
      onSuccess={() => confirm("Thresholds updated for " + item.item_name + ".")}
    >
      {({ pending }) => (
        <>
          <Field
            label="Safety threshold"
            htmlFor="min_safety_threshold"
            hint="The line is flagged once available stock falls below this."
            required
          >
            <Input
              id="min_safety_threshold"
              name="min_safety_threshold"
              type="number"
              min={0}
              step="0.01"
              inputMode="decimal"
              required
              defaultValue={item.min_safety_threshold}
              className={NUMERIC}
              disabled={pending}
            />
          </Field>

          <Field
            label="Total stock"
            htmlFor="total_stock"
            hint="Change only when the sanctioned capacity itself changed."
          >
            <Input
              id="total_stock"
              name="total_stock"
              type="number"
              min={0}
              step="0.01"
              inputMode="decimal"
              defaultValue={item.total_stock}
              className={NUMERIC}
              disabled={pending}
            />
          </Field>

          <Field label="Expires on" htmlFor="expires_on" hint="Optional.">
            <Input
              id="expires_on"
              name="expires_on"
              type="date"
              defaultValue={item.expires_on ?? ""}
              className={NUMERIC}
              disabled={pending}
            />
          </Field>
        </>
      )}
    </FormDialog>
  );
}

/** Both stock actions for one line. */
export function StockActions({ item }: { item: InventoryItem }) {
  return (
    <div className="flex flex-wrap items-center justify-end gap-1">
      <RestockDialog item={item} />
      <EditThresholdDialog item={item} />
    </div>
  );
}
