"use client";

import { Plus, Receipt, Trash2, Wallet } from "lucide-react";
import { useState } from "react";

import { createBill, recordPayment } from "@/app/(hospital)/hospital/actions";
import { Button } from "@/components/ui/button";
import { FormDialog } from "@/components/ui/dialog";
import { Field, Input, Select } from "@/components/ui/field";
import { useToast } from "@/components/ui/toast";
import { humanise, money } from "@/lib/format";
import type { Bill, PatientCase, PaymentMode } from "@/lib/types";

/**
 * Invoicing.
 *
 * An invoice is created whole: the platform has no endpoint that appends a
 * charge to an existing one, and a bill with no charges is not a bill. So the
 * composer collects every line first and submits once.
 *
 * Every figure below is computed in integer paise from the strings the cashier
 * typed, never through `parseFloat`. The preview has to agree with the server's
 * Decimal arithmetic to the last paisa, or the cashier stops trusting the
 * screen. The server's total remains the authoritative one.
 */

const PAYMENT_MODES: PaymentMode[] = [
  "CASH",
  "CARD",
  "UPI",
  "NET_BANKING",
  "INSURANCE",
  "GOVT_SCHEME",
];

const NUMERIC = "font-mono tabular-nums";

/** Parse a decimal string into an integer scaled by 10^places. Null if unusable. */
function scaled(value: string, places: number): number | null {
  const text = value.trim();
  if (text === "" || !/^\d*\.?\d*$/.test(text)) return null;

  const [whole, fraction = ""] = text.split(".");
  const padded = fraction.padEnd(places, "0").slice(0, places);
  const combined = (whole === "" ? "0" : whole) + padded;
  const parsed = Number(combined);
  return Number.isSafeInteger(parsed) ? parsed : null;
}

/** Render integer paise back as a decimal string, so `money()` can group it. */
function fromPaise(paise: number): string {
  const negative = paise < 0;
  const absolute = Math.abs(paise);
  const text = String(absolute).padStart(3, "0");
  const result = text.slice(0, -2) + "." + text.slice(-2);
  return negative ? "-" + result : result;
}

interface Line {
  key: number;
  description: string;
  rate: string;
  quantity: string;
}

const BLANK: Omit<Line, "key"> = { description: "", rate: "", quantity: "1" };

export function CreateInvoiceDialog({
  hospitalId,
  suggestedInvoiceNo,
  cases,
  patientNames,
}: {
  hospitalId: string;
  suggestedInvoiceNo: string;
  cases: PatientCase[];
  patientNames: Record<string, string>;
}) {
  const { confirm } = useToast();
  const [lines, setLines] = useState<Line[]>([{ key: 0, ...BLANK }]);
  const [nextKey, setNextKey] = useState(1);
  const [tax, setTax] = useState("0.00");
  const [discount, setDiscount] = useState("0.00");
  const [caseId, setCaseId] = useState(cases[0]?._id ?? "");

  function addLine() {
    setLines((current) => [...current, { key: nextKey, ...BLANK }]);
    setNextKey((key) => key + 1);
  }

  function removeLine(key: number) {
    setLines((current) => (current.length === 1 ? current : current.filter((l) => l.key !== key)));
  }

  function editLine(key: number, patch: Partial<Line>) {
    setLines((current) =>
      current.map((line) => (line.key === key ? { ...line, ...patch } : line)),
    );
  }

  // Rate carries two decimals, quantity three. Multiplying the scaled integers
  // gives paise x 1000, so divide back down and round half-up once, exactly
  // where the backend's `money()` rounds.
  function lineTotalPaise(line: Line): number | null {
    const ratePaise = scaled(line.rate, 2);
    const quantityMilli = scaled(line.quantity, 3);
    if (ratePaise === null || quantityMilli === null) return null;
    return Math.round((ratePaise * quantityMilli) / 1000);
  }

  const subtotalPaise = lines.reduce((sum, line) => sum + (lineTotalPaise(line) ?? 0), 0);
  const taxPaise = scaled(tax, 2) ?? 0;
  const discountPaise = scaled(discount, 2) ?? 0;
  const grandTotalPaise = subtotalPaise + taxPaise - discountPaise;
  const discountTooLarge = discountPaise > subtotalPaise;

  // Every case is invoiceable, open or closed: a discharged patient still has
  // a bill to settle, and that is the common one.
  const chosenCase = cases.find((item) => item._id === caseId);

  if (cases.length === 0) {
    return (
      <Button size="sm" disabled title="There is no case to invoice yet.">
        <Plus strokeWidth={1.75} aria-hidden="true" />
        Raise invoice
      </Button>
    );
  }

  return (
    <FormDialog
      size="lg"
      trigger={
        <Button size="sm">
          <Receipt strokeWidth={1.75} aria-hidden="true" />
          Raise invoice
        </Button>
      }
      title="Raise an invoice"
      description="Charges are fixed once the invoice is raised, so add every line before saving."
      submitLabel="Raise invoice"
      pendingLabel="Raising"
      action={(formData) => {
        formData.set("patient_id", chosenCase?.patient_id ?? "");
        return createBill(hospitalId, formData);
      }}
      validate={() =>
        discountTooLarge
          ? "The discount cannot exceed the subtotal being charged."
          : null
      }
      onSuccess={() => confirm("Invoice raised.")}
    >
      {({ pending }) => (
        <>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Case" htmlFor="case_id" required>
              <Select
                id="case_id"
                name="case_id"
                value={caseId}
                onChange={(event) => setCaseId(event.target.value)}
                required
                disabled={pending}
              >
                {cases.map((item) => (
                  <option key={item._id} value={item._id}>
                    {item.case_number} - {patientNames[item.patient_id] ?? "Patient"}
                  </option>
                ))}
              </Select>
            </Field>

            <Field
              label="Invoice number"
              htmlFor="invoice_no"
              hint="Unique within this hospital."
              required
            >
              <Input
                id="invoice_no"
                name="invoice_no"
                required
                minLength={3}
                maxLength={40}
                defaultValue={suggestedInvoiceNo}
                className={NUMERIC}
                disabled={pending}
              />
            </Field>
          </div>

          <fieldset className="rounded-md border border-border">
            <legend className="ml-3 px-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Charges
            </legend>

            <div className="divide-y divide-border">
              {lines.map((line, index) => {
                const totalPaise = lineTotalPaise(line);
                return (
                  <div key={line.key} className="flex items-end gap-2 px-3 py-2.5">
                    <div className="min-w-0 flex-[3]">
                      <label
                        htmlFor={"line_description_" + line.key}
                        className="mb-1 block text-xs text-muted-foreground"
                      >
                        Description
                      </label>
                      <Input
                        id={"line_description_" + line.key}
                        name="line_description"
                        value={line.description}
                        onChange={(event) =>
                          editLine(line.key, { description: event.target.value })
                        }
                        disabled={pending}
                        placeholder={index === 0 ? "Ward charges" : "Pharmacy"}
                      />
                    </div>

                    <div className="w-24 shrink-0">
                      <label
                        htmlFor={"line_rate_" + line.key}
                        className="mb-1 block text-xs text-muted-foreground"
                      >
                        Rate
                      </label>
                      <Input
                        id={"line_rate_" + line.key}
                        name="line_rate"
                        inputMode="decimal"
                        value={line.rate}
                        onChange={(event) => editLine(line.key, { rate: event.target.value })}
                        className={NUMERIC}
                        disabled={pending}
                        placeholder="2500.00"
                      />
                    </div>

                    <div className="w-20 shrink-0">
                      <label
                        htmlFor={"line_quantity_" + line.key}
                        className="mb-1 block text-xs text-muted-foreground"
                      >
                        Qty
                      </label>
                      <Input
                        id={"line_quantity_" + line.key}
                        name="line_quantity"
                        inputMode="decimal"
                        value={line.quantity}
                        onChange={(event) =>
                          editLine(line.key, { quantity: event.target.value })
                        }
                        className={NUMERIC}
                        disabled={pending}
                      />
                    </div>

                    <div className="w-28 shrink-0 pb-2 text-right">
                      <span className={NUMERIC + " text-sm text-foreground"}>
                        {totalPaise === null ? "-" : money(fromPaise(totalPaise))}
                      </span>
                    </div>

                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      className="mb-0.5 shrink-0"
                      onClick={() => removeLine(line.key)}
                      disabled={pending || lines.length === 1}
                      aria-label={"Remove line " + (index + 1)}
                    >
                      <Trash2 strokeWidth={1.75} aria-hidden="true" />
                    </Button>
                  </div>
                );
              })}
            </div>

            <div className="border-t border-border px-3 py-2.5">
              <Button
                type="button"
                variant="secondary"
                size="sm"
                onClick={addLine}
                disabled={pending}
              >
                <Plus strokeWidth={1.75} aria-hidden="true" />
                Add charge
              </Button>
            </div>
          </fieldset>

          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Tax" htmlFor="tax_amount">
              <Input
                id="tax_amount"
                name="tax_amount"
                inputMode="decimal"
                value={tax}
                onChange={(event) => setTax(event.target.value)}
                className={NUMERIC}
                disabled={pending}
              />
            </Field>

            <Field
              label="Discount"
              htmlFor="discount_amount"
              error={discountTooLarge ? "A discount cannot exceed the subtotal." : null}
            >
              <Input
                id="discount_amount"
                name="discount_amount"
                inputMode="decimal"
                value={discount}
                onChange={(event) => setDiscount(event.target.value)}
                className={NUMERIC}
                disabled={pending}
              />
            </Field>
          </div>

          <dl className="divide-y divide-border rounded-md border border-border">
            <div className="flex justify-between px-3 py-2 text-sm">
              <dt className="text-muted-foreground">Subtotal</dt>
              <dd className={NUMERIC + " text-foreground"}>{money(fromPaise(subtotalPaise))}</dd>
            </div>
            <div className="flex justify-between px-3 py-2 text-sm">
              <dt className="text-muted-foreground">Tax</dt>
              <dd className={NUMERIC + " text-foreground"}>{money(fromPaise(taxPaise))}</dd>
            </div>
            <div className="flex justify-between px-3 py-2 text-sm">
              <dt className="text-muted-foreground">Discount</dt>
              <dd className={NUMERIC + " text-foreground"}>
                {discountPaise > 0 ? "-" : ""}
                {money(fromPaise(discountPaise))}
              </dd>
            </div>
            <div className="flex justify-between px-3 py-2.5">
              <dt className="text-sm font-semibold text-foreground">Grand total</dt>
              <dd className={NUMERIC + " text-sm font-semibold text-foreground"}>
                {money(fromPaise(grandTotalPaise))}
              </dd>
            </div>
          </dl>
        </>
      )}
    </FormDialog>
  );
}

export function RecordPaymentDialog({ bill }: { bill: Bill }) {
  const { confirm } = useToast();
  const settled = bill.payment_status === "PAID";

  if (settled) {
    return <span className="text-xs text-muted-foreground">Settled</span>;
  }

  return (
    <FormDialog
      trigger={
        <Button variant="ghost" size="sm">
          <Wallet strokeWidth={1.75} aria-hidden="true" />
          Record payment
        </Button>
      }
      title="Record a payment"
      description={"Invoice " + bill.invoice_no}
      submitLabel="Record payment"
      action={(formData) => recordPayment(bill._id, formData)}
      onSuccess={() => confirm("Payment recorded against " + bill.invoice_no + ".")}
    >
      {({ pending }) => (
        <>
          <dl className="divide-y divide-border rounded-md border border-border">
            <div className="flex justify-between px-3 py-2 text-sm">
              <dt className="text-muted-foreground">Invoiced</dt>
              <dd className={NUMERIC + " text-foreground"}>{money(bill.grand_total)}</dd>
            </div>
            <div className="flex justify-between px-3 py-2 text-sm">
              <dt className="text-muted-foreground">Already paid</dt>
              <dd className={NUMERIC + " text-foreground"}>{money(bill.amount_paid)}</dd>
            </div>
          </dl>

          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Amount received" htmlFor="amount" required>
              <Input
                id="amount"
                name="amount"
                inputMode="decimal"
                required
                className={NUMERIC}
                disabled={pending}
                placeholder="1500.00"
              />
            </Field>

            <Field label="Method" htmlFor="payment_mode" required>
              <Select id="payment_mode" name="payment_mode" required disabled={pending}>
                {PAYMENT_MODES.map((mode) => (
                  <option key={mode} value={mode}>
                    {humanise(mode)}
                  </option>
                ))}
              </Select>
            </Field>
          </div>

          <Field
            label="Reference"
            htmlFor="reference"
            hint="Optional. Transaction id, cheque number, or claim number."
          >
            <Input
              id="reference"
              name="reference"
              maxLength={100}
              className="font-mono"
              disabled={pending}
            />
          </Field>
        </>
      )}
    </FormDialog>
  );
}
