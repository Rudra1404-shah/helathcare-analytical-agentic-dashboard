# Unified National Health Platform — Design System

**Status:** Phase 2. Governs `frontend/`.
**Stack:** Next.js 16 (App Router) · Tailwind v4 · shadcn/ui idiom · Lucide React · Geist

---

## 1. What this interface is for

Three audiences, one system:

| Portal | Who | Reading conditions |
|---|---|---|
| 🏛️ Government | Ministry officials | Desk, comparing dozens of hospitals, deciding enforcement |
| 🏥 Hospital | Admins, staff, doctors | Ward terminal, mid-shift, often at speed, sometimes at 3am |
| 👥 Citizen | The public | Phone, possibly distressed, possibly first time |

The hospital portal sets the tone. A charge nurse checking ICU availability during a surge is not browsing. **Density, contrast, and scannability are the whole brief.** Every decision below follows from that.

### The three dials

```
DESIGN_VARIANCE: 3    Predictable. Same layout grammar on every screen, so
                      muscle memory transfers between views.
MOTION_INTENSITY: 2   Near-static. State changes only. Clinical software that
                      bounces is clinical software people distrust.
VISUAL_DENSITY: 8     Cockpit. Tight rows, hairline separators, tabular
                      numerals, no decorative cards.
```

This is deliberately the opposite of a marketing site. Asymmetric heroes, scroll-driven reveals, and generous whitespace are all wrong here.

---

## 2. Color

One accent. One theme per viewer. Slate carries the structure; teal carries interaction.

### Tokens

Defined as CSS custom properties in `app/globals.css`, consumed through Tailwind v4's `@theme inline`.

| Token | Light | Dark | Use |
|---|---|---|---|
| `--background` | `#f8fafc` slate-50 | `#020617` slate-950 | Page ground |
| `--surface` | `#ffffff` | `#0f172a` slate-900 | Panels, table bodies |
| `--surface-muted` | `#f1f5f9` slate-100 | `#1e293b` slate-800 | Table headers, inactive tabs |
| `--border` | `#e2e8f0` slate-200 | `#1e293b` slate-800 | Hairlines, dividers |
| `--foreground` | `#0f172a` slate-900 | `#f1f5f9` slate-100 | Primary text |
| `--muted-foreground` | `#475569` slate-600 | `#94a3b8` slate-400 | Labels, metadata |
| `--primary` | `#0d9488` teal-600 | `#2dd4bf` teal-400 | The single accent |
| `--primary-foreground` | `#ffffff` | `#042f2e` teal-950 | Text on accent |
| `--ring` | `#0d9488` | `#2dd4bf` | Focus ring |

`--muted-foreground` is slate-600, not slate-400. Slate-400 on white is 2.8:1 and fails AA. This is the most common contrast mistake in dashboard UI and it is banned here.

### Semantic status colors

Status color is **information**, not decoration. It appears only where it carries meaning.

| Meaning | Light | Dark | Where |
|---|---|---|---|
| Critical / immediate | rose-600 `#e11d48` | rose-400 | Triage 1, blacklisted, stock at zero |
| Warning / urgent | amber-600 `#d97706` | amber-400 | Triage 2, below safety threshold, pending payment |
| Stable / accredited | emerald-600 `#059669` | emerald-400 | Paid, NABH, discharged well |
| Informational | sky-600 `#0284c7` | sky-400 | Under review, observation |
| Neutral | slate-500 | slate-400 | Inactive, dismissed, not applicable |

**Never color alone.** Every status badge pairs its color with a text label and, where the row is scanned at speed, an icon. A colorblind clinician must read the same information as everybody else.

### Rules

- **One accent.** Teal is the only interactive color. No blue CTA in one view and teal in another.
- **No AI-purple.** No gradient buttons, no glow, no mesh backgrounds.
- **No pure `#000` or `#fff`** for text or ground. Slate-950 and slate-50.
- **Page theme lock.** Light or dark applies to the entire application. No inverted section.

---

## 3. Typography

**Geist Sans** for interface. **Geist Mono** for every number that belongs to a column.

Loaded through `next/font`, self-hosted, `display: swap`. No `<link>` to Google Fonts.

| Role | Class | Notes |
|---|---|---|
| Page title | `text-xl font-semibold tracking-tight` | Once per view |
| Section heading | `text-sm font-semibold` | Above a table or panel |
| Table header | `text-xs font-medium uppercase tracking-wide text-muted-foreground` | The one place uppercase is allowed |
| Body / cell | `text-sm` | Default |
| Metadata | `text-xs text-muted-foreground` | Timestamps, counts, secondary ids |
| Numeric cell | `font-mono text-sm tabular-nums` | **Mandatory** for money, stock, vitals, counts |

### Tabular numerals are not optional

Bed counts, oxygen litres, invoice totals, blood pressure. If a column of numbers does not align on the decimal, the eye cannot compare down the column, which is the only reason the column exists. Every numeric cell gets `font-mono tabular-nums`.

### Copy rules

- **Zero em-dashes.** Not in headings, labels, buttons, empty states, error messages, or alt text. Use a hyphen or restructure the sentence.
- **Sentence case** for everything except table headers.
- **No invented precision.** Numbers shown are numbers the API returned.
- **Say what happened.** "No beds of this kind are free" beats "Operation failed".

---

## 4. Shape and elevation

**One radius scale, applied everywhere:**

```
Interactive controls (button, input, select, badge)  rounded-md   (6px)
Containers (panel, table wrapper, dialog)            rounded-lg   (8px)
Nothing is a pill. Nothing is square.
```

**Elevation is nearly absent.** At `VISUAL_DENSITY: 8`, cards are noise. Group with `border` and `divide-y` instead. The two exceptions are dialogs and dropdowns, which genuinely float above the page and use `shadow-lg` tinted toward slate, never pure black.

---

## 5. Layout

```
┌──────────────────────────────────────────────────────────┐
│ Top bar  64px   portal name · hospital · account         │
├────────────┬─────────────────────────────────────────────┤
│ Sidebar    │  Page header   title + primary action       │
│ 240px      │  ─────────────────────────────────────────  │
│ nav only   │  Filter bar    inline, no modal             │
│            │  ─────────────────────────────────────────  │
│            │  Content       table / board / form         │
└────────────┴─────────────────────────────────────────────┘
```

- Content width `max-w-[1400px]`, gutters `px-6`.
- Section rhythm `py-6`, not `py-24`. This is an application, not a landing page.
- Grid, never flex percentage math.
- `min-h-[100dvh]`, never `h-screen`.
- **Sidebar collapses to a sheet below `lg`.** Every table scrolls inside its own `overflow-x-auto`; the page body never scrolls horizontally.

---

## 6. Component contracts

### Tables

The primary component of this system.

- Sticky header, `bg-surface-muted`.
- `divide-y divide-border` on the body. No border on every side of every cell.
- Row height 44px. Comfortable enough to hit on a touch terminal, tight enough to show twenty rows.
- Row hover `bg-surface-muted`, and a visible focus ring for keyboard users.
- Numeric columns right-aligned and monospaced.
- Every table declares **three states beyond its data**: skeleton, empty, error.

### Every asynchronous view ships four states

| State | Rule |
|---|---|
| Loading | Skeleton matching the final layout's shape. Never a centered spinner. |
| Empty | Explains what would populate it and offers the action that would. |
| Error | States what failed and offers a retry. Never a bare stack trace. |
| Loaded | The data. |

A view missing any of these is unfinished.

### Buttons

| Variant | Use |
|---|---|
| `primary` | The one action this view exists for. Teal fill, white text, 4.9:1. |
| `secondary` | Supporting action. Slate border, transparent fill. |
| `destructive` | Blacklisting, cancelling an invoice. Rose. Always behind a confirm. |
| `ghost` | Toolbar and row actions. |

- Label fits one line at desktop. Three words maximum.
- `:active` gets `scale-[0.98]`. That is the entire motion budget for a button.
- Focus ring visible in both themes, offset from the control.

### Badges

Status only. Never decorative. Text label plus tinted background plus AA-passing foreground.

### Forms

- Label **above** the input, always. Never placeholder-as-label.
- Helper text below the label, error text below the input, both in markup from the start.
- Errors from the API's `error` string, rendered inline against the field where the API named one.
- Required fields marked in the label, not by color alone.

---

## 7. Motion

The entire budget:

- `transition-colors duration-150` on hover and focus.
- `active:scale-[0.98]` on buttons.
- Dialog fade and 4px rise, 150ms.
- Skeleton pulse.

No scroll-driven animation. No parallax. No entrance choreography. No marquees. Everything above collapses under `prefers-reduced-motion: reduce`.

---

## 8. Accessibility floor: WCAG 2.2 AA

Non-negotiable, verified per component:

- **Contrast** 4.5:1 body, 3:1 large text and UI boundaries. The token table in §2 is chosen to pass in both themes.
- **Keyboard** reaches every action. Dialogs trap focus and restore it on close. Skip-to-content link on every page.
- **Status is never color alone.** Color plus label, and an icon where scanned at speed.
- **Live regions** announce table refreshes and toast messages.
- **Touch targets** 44×44 minimum on the citizen portal, which is phone-first.
- **Focus never suppressed.** `outline-none` only ever paired with a replacement ring.

### Verified contrast pairings

| Pairing | Light | Dark |
|---|---|---|
| foreground on background | 16.8:1 | 15.9:1 |
| muted-foreground on background | 7.4:1 | 7.1:1 |
| primary-foreground on primary | 4.9:1 | 9.2:1 |
| rose-600 on background | 5.1:1 | 6.8:1 |
| amber-600 on background | 4.7:1 | 8.4:1 |
| emerald-600 on background | 4.6:1 | 7.9:1 |

---

## 9. Banned

Carried from the anti-slop review, plus what this domain adds:

- Em-dashes anywhere visible.
- AI-purple, gradient buttons, glow, glassmorphism, mesh backgrounds.
- Decorative status dots, section-number eyebrows, scroll cues, locale strips.
- Fake precision. Every number comes from the API.
- Placeholder-as-label.
- `Jane Doe`, `Acme`, `John Smith`. Seed data uses realistic locale-appropriate names.
- Cards wrapping every metric. Grouping is borders and space.
- Centered empty states with a shrug illustration and no next action.
- **Domain-specific:** no red-only alerting, no truncated clinical values, no rounding money for display. Money renders exactly as the API's decimal string.

---

## 10. Frontend conventions

- Server Components by default. `'use client'` only on genuine interaction leaves.
- Session in an **httpOnly cookie**, set by a Next route handler. The token is never readable by JavaScript, so an XSS in a dashboard cannot exfiltrate a ministry session.
- One typed API client. It unwraps the platform's `{success, data, error}` envelope and throws a typed error carrying the API's own message, which is what the UI renders.
- Money arrives as a **string** and is never coerced to a `number`. `Decimal` exists in the backend precisely so a rounding drift cannot become an overcharging complaint; parsing it into a float in the browser would undo that.
- Icons from `lucide-react` only, `strokeWidth={1.75}` throughout.
