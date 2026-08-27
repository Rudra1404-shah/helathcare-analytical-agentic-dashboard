/**
 * Display formatting.
 *
 * Money is formatted from the API's decimal **string** and never parsed into a
 * float. `Decimal` exists in the backend precisely so a rounding drift cannot
 * become an Overcharging complaint; `parseFloat` in the browser would undo it.
 */

const INR = "₹";

/**
 * Render a decimal string as currency, grouping the integer part.
 *
 * Operates on the string itself: "10528.13" becomes "₹10,528.13" with the
 * fractional digits untouched.
 */
export function money(amount: string | null | undefined): string {
  if (amount === null || amount === undefined || amount === "") return `${INR}0.00`;

  const negative = amount.startsWith("-");
  const unsigned = negative ? amount.slice(1) : amount;
  const [whole, fraction = "00"] = unsigned.split(".");
  const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ",");

  return `${negative ? "-" : ""}${INR}${grouped}.${fraction.padEnd(2, "0").slice(0, 2)}`;
}

/** Render a quantity with its unit, dropping a meaningless trailing zero. */
export function quantity(value: number, unit?: string | null): string {
  const rendered = Number.isInteger(value) ? String(value) : value.toFixed(2);
  return unit ? `${rendered} ${unit.toLowerCase()}` : rendered;
}

/** Render a percentage from a 0..1 ratio. */
export function percent(ratio: number): string {
  return `${Math.round(ratio * 100)}%`;
}

const DATE_TIME = new Intl.DateTimeFormat("en-IN", {
  day: "2-digit",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

const DATE_ONLY = new Intl.DateTimeFormat("en-IN", {
  day: "2-digit",
  month: "short",
  year: "numeric",
});

export function dateTime(iso: string | null | undefined): string {
  if (!iso) return "Not recorded";
  return DATE_TIME.format(new Date(iso));
}

export function dateOnly(iso: string | null | undefined): string {
  if (!iso) return "Not recorded";
  return DATE_ONLY.format(new Date(iso));
}

/** How long ago, in the coarsest unit that is still informative. */
export function relative(iso: string | null | undefined): string {
  if (!iso) return "Not recorded";
  const elapsed = Date.now() - new Date(iso).getTime();
  const minutes = Math.round(elapsed / 60_000);

  if (minutes < 1) return "Just now";
  if (minutes < 60) return `${minutes} min ago`;

  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} h ago`;

  const days = Math.round(hours / 24);
  if (days < 31) return `${days} d ago`;

  return dateOnly(iso);
}

/** Length of stay, for a case that may or may not have closed. */
export function stayDuration(admitted: string, discharged: string | null): string {
  const end = discharged ? new Date(discharged).getTime() : Date.now();
  const hours = Math.max(0, Math.round((end - new Date(admitted).getTime()) / 3_600_000));

  if (hours < 24) return `${hours} h`;
  const days = Math.floor(hours / 24);
  const remainder = hours % 24;
  return remainder === 0 ? `${days} d` : `${days} d ${remainder} h`;
}

/** Turn an enum member into readable text: ICU_BEDS becomes "ICU beds". */
export function humanise(value: string): string {
  const spaced = value.replace(/_/g, " ").toLowerCase();
  const capitalised = spaced.charAt(0).toUpperCase() + spaced.slice(1);
  return capitalised
    .replace(/\bIcu\b/gi, "ICU")
    .replace(/\bNabh\b/gi, "NABH")
    .replace(/\bUpi\b/gi, "UPI")
    .replace(/\bSpo2\b/gi, "SpO2");
}

/** Initials for an avatar-free identity chip. */
export function initials(fullName: string): string {
  const parts = fullName.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}
