"use client";

import { Printer } from "lucide-react";

import { Button } from "@/components/ui/button";

/** Prints the receipt. The print stylesheet drops the application chrome. */
export function PrintButton() {
  return (
    <Button variant="secondary" size="sm" onClick={() => window.print()}>
      <Printer strokeWidth={1.75} aria-hidden="true" />
      Print receipt
    </Button>
  );
}
