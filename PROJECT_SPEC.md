# Unified National Health Platform — Project Specification

**Status:** Phase 2 complete (HTTP API and three-portal dashboard)
**Stack:** FastAPI · MongoDB · Beanie 2.2 ODM · PyMongo async · Pydantic v2 · Python 3.11
**Frontend:** Next.js 16 App Router · Tailwind v4 · shadcn/ui idiom · Lucide · Geist

---

## 1. Problem Statement & System Vision

> Bridging the gap between Public (Government) and Private healthcare ecosystems into a
> Unified National Health Platform for the Health Ministry, Hospitals, and Citizens.

Today, bed availability, staff hierarchy, inventory, and patient medical histories are
fragmented across private and public hospitals. A citizen treated at a public hospital in one
state and a private hospital in another has two disconnected records. A ministry official
cannot see, in one place, how many ICU beds a district actually has free. A surge in one
disease across three neighbouring hospitals is invisible until it is a crisis.

This platform centralises:

1. **Healthcare governance** — hospital verification, accreditation, and enforcement
2. **Hospital operational workflows** — departments, workforce, patients, cases, inventory, billing
3. **Patient health records** — one unified cross-hospital history per citizen
4. **Public grievance resolution** — evidence-backed complaints with a ministry investigation trail

…and lays the data foundation for a future **7-module AI analytical intelligence engine**.

### The future analytics engine (Phase 4+)

Every model in this specification was shaped by what these modules will need to read:

| # | Module | Primary data dependency |
|---|---|---|
| 1 | Real-time monitoring | `patient_cases.status`, `hospital_inventory.available_stock` |
| 2 | Outbreak anomaly detection | `case_types.is_notifiable`, `patient_cases.case_type_id` + `admitted_at`, `zones.population_covered` |
| 3 | 7–14 day surge forecasting | `patient_cases.admitted_at` time series per zone, per capita |
| 4 | Workforce reallocation | `doctors.max_daily_patients`, `staff.shift`, `staff.status` |
| 5 | Resource prediction | `hospital_inventory` levels + consumption velocity |
| 6 | 4-tier Smart Alerts | `hospital_inventory.min_safety_threshold` breaches |
| 7 | Impact tracking | `complaints.action_taken` correlated against later case and inventory outcomes |

This is why `zones` is a first-class collection (modules 2 and 3 need a per-capita denominator),
why vitals are stored as a **list** rather than a snapshot (deterioration is only visible as a
trend), and why timestamps are mandatory on every document.

---

## 2. The Three Portals

### A. Government (Health Ministry)

| # | Form | Backing collection(s) |
|---|---|---|
| A1 | Master Govt Login (Official Email, Password) | `users` |
| A2 | Hospital Verification & Accreditation | `hospitals` |
| A3 | Zone/Area Management | `zones` |
| A4 | Complaint Investigation & Resolution | `complaints` |

**A2 fields** — Hospital Name, License No, Sector Type (PUBLIC/PRIVATE/TRUST), State, City,
Zone/Ward Area, Geo-Coordinates, Total Sanctioned Beds, ICU Beds, Ventilators, Oxygen Bulk
Capacity (Litres), Accreditation Status (NABH / State Licensed / Pending / Blacklisted),
Nodal Officer Assigned.

**A4 fields** — Complaint ID, Evidence Viewer (photo/video preview), Investigation Status
(Submitted / Under Review / Inquiry Assigned / Action Taken / Dismissed), Hospital Explanation,
Action Taken (Warning / Fine / License Suspension / Dismissed), Closure Remarks.

### B. Hospital — 10 Operational Modules

| # | Form | Backing collection |
|---|---|---|
| B1 | Hospital Profile & Infrastructure Setup | `hospitals` |
| B2 | Department Registration | `departments` |
| B3 | Admin & Support Staff Intake | `staff` |
| B4 | Medical Staff Intake | `staff` |
| B5 | Doctor Onboarding | `doctors` |
| B6 | Patient Intake (manual + Excel bulk upload) | `patients` |
| B7 | Case Type Definition | `case_types` |
| B8 | Patient Case / Encounter | `patient_cases` |
| B9 | Hospital Inventory | `hospital_inventory` |
| B10 | Billing | `bills` |

**B3 roles** — Cleaner, Security, Driver, Desk Admin, Liftman, Helper, Admin, Accountant.
**B4 roles** — Staff Nurse, Matron, Lab Assistant, Ward Boy, Compounder.
**Shifts** — Morning, Evening, Night, General.

**B8 fields** — Case ID, Patient ID, Doctor ID, Department ID, Bed Allocated, Admission Time,
Chief Symptoms, Vitals (BP, Pulse, SpO2, Temp), Prescriptions, Case Status (Admitted / ICU /
Observation / Discharged / Deceased), Discharge Summary.

**B9 categories** — General Beds, ICU Beds, Ventilators, Oxygen Cylinders, Oxygen Litres,
Medicines, Consumables.

### C. Citizen / Public

| # | Form | Backing collection |
|---|---|---|
| C1 | Citizen Registration & Login | `users` |
| C2 | Public Complaint (**mandatory evidence**) | `complaints` |
| C3 | Personal Health Record (PHR) Access & Export | read-only across `patients` + `patient_cases` + `bills` |

**C2 categories** — Overcharging, Bed Refusal, Negligence, Hygiene, Shortage, False Billing.
Description minimum 50 characters. **At least one photo or video is required to submit.**

---

## 3. MongoDB Collections (12)

| Collection | Model | Purpose |
|---|---|---|
| `users` | `User` | Auth, Argon2 hashes, roles |
| `zones` | `Zone` | Administrative areas + population |
| `hospitals` | `Hospital` | Profile, accreditation, capacity, geo |
| `departments` | `Department` | Department registry, HOD link |
| `staff` | `Staff` | Admin/support **and** medical staff |
| `doctors` | `Doctor` | Specialisations, shifts, licences |
| `patients` | `Patient` | Unified patient identity |
| `case_types` | `CaseType` | Disease classification, ICD-10, triage |
| `patient_cases` | `PatientCase` | Admissions, vitals, discharge |
| `hospital_inventory` | `InventoryItem` | Resources and alert thresholds |
| `bills` | `Bill` | Itemised invoices |
| `complaints` | `Complaint` | Grievances + investigation trail |

> **`zones` was added during Phase 1.** The original brief listed a Zone/Area Management Form
> but only eleven collections. Population-per-zone is a required input for outbreak detection
> and surge forecasting, so it needs to persist rather than live as a string on `hospitals`.

### Design decisions

**One `staff` collection, not two.** The admin/support and medical intake forms share ~80% of
their fields. A single collection carries both, discriminated by `staff_category`, with a
validator asserting the role actually belongs to the declared category and a second requiring a
nursing/pharmacy registration number for medical staff. Doctors stay separate — they carry
council licences, specialisations, and patient caps that support staff do not.

**`PydanticObjectId` references, not Beanie `Link`.** Links require a live `init_beanie` to
resolve and invite N+1 fetches. Plain ID references keep the domain layer independent of
connection state.

**National IDs are never stored in plaintext.** Each is stored as a `ProtectedNationalId`:
AES-GCM ciphertext (recoverable, for the citizen's own PHR view) plus a deterministic
HMAC-SHA256 lookup hash (indexable, for cross-hospital identity resolution). Formatting
variants — `1234-5678-9012`, `1234 5678 9012`, `123456789012` — all normalise to the same
lookup hash, which is what makes the unified record work in practice.

**Money uses `Decimal`, never `float`.** A rounding drift in billing surfaces directly as an
Overcharging or False Billing complaint.

**Uniqueness is hospital-scoped where it should be.** MRNs, employee IDs, department codes,
case numbers, and invoice numbers are unique *within a hospital* via compound indexes. Licence
numbers and complaint numbers are unique platform-wide.

---

## 4. Architecture

```
src/
  main.py                    App factory, CORS, exception handlers, /uploads mount
  core/
    config.py                pydantic-settings; UNHP_ prefix; placeholder-secret guard
    security.py              Argon2 passwords; AES-GCM + HMAC National IDs
    tokens.py                JWT issue and verify; signed role and hospital claims
    errors.py                DomainError hierarchy carrying its own HTTP status
    audit.py                 Structured audit events on the unhp.audit logger
  infrastructure/
    database.py              THE ONLY module that touches the MongoDB driver
  domain/
    enums.py                 Every controlled vocabulary
    types.py                 Reusable constrained field types, including Money
    models/                  12 Beanie documents + value objects
    schemas/                 Pydantic v2 request/response per form
  services/                  15 modules: the business rules, framework-free
  api/
    deps.py                  Auth, role guards, hospital-scope guard, paging
    errors.py                Every failure normalised into the response envelope
    v1/                      14 routers, 76 routes
scripts/
  seed.py                    Synthetic demonstration data
tests/
  conftest.py                DB-free Beanie bootstrap for unit tests
  factories.py               Valid-by-default builders (synthetic data only)
  unit/                      414 tests, no database required
  integration/               91 tests against a live MongoDB
frontend/
  app/                       Three role-gated portals, App Router
  components/                Shell, UI primitives, domain components
  lib/                       Typed API client, session, formatting
```

### A note on the driver

The original brief specified **Motor**. Beanie 2.x dropped Motor entirely: it now requires
`pymongo>=4.11` and uses PyMongo's native `AsyncMongoClient`. MongoDB folded Motor's async
support back into PyMongo and Motor reached end of life, so `AsyncMongoClient` *is* the current
async driver rather than a substitute for one. All driver contact is confined to
`infrastructure/database.py`, so a future migration is a single-file change.

### Two-layer validation

Critical rules are enforced **twice** — once on the request schema (so the API fails early with
a friendly message) and once on the stored model (so no code path can bypass it):

| Rule | Schema layer | Model layer |
|---|---|---|
| Complaint evidence mandatory | `ComplaintSubmissionRequest` | `Complaint` |
| ICU + emergency ≤ sanctioned beds | `HospitalCapacityPayload` | `HospitalCapacity` |
| Available ≤ total stock | `InventoryItemCreateRequest` | `InventoryItem` |
| Systolic > diastolic | `VitalSignsRequest` | `VitalSigns` |
| Staff role matches category | both intake schemas | `Staff` |

Documents also set `validate_assignment=True`, so mutation cannot turn a valid document into an
invalid one — emptying a complaint's evidence after construction raises rather than silently
persisting.

---

## 5. Validation Rules Enforced

| Rule | Location |
|---|---|
| Complaint evidence list non-empty | `complaint.py` model + schema |
| Complaint description ≥ 50 chars | both layers |
| Evidence MIME type matches declared photo/video kind | `EvidenceAttachmentRequest` |
| Incident date not in the future | both layers |
| Closed investigation requires action + remarks | both layers |
| Triage level ∈ 1–4 | `TriageLevel` IntEnum |
| ICD-10 code format | `Icd10Code` |
| `available_stock ≤ total_stock`, `≥ 0` | both layers |
| Line total = rate × quantity | `BillLineItem` |
| Subtotal = Σ line totals | `Bill` |
| Grand total = subtotal + tax − discount | `Bill` |
| Discount ≤ subtotal; paid ≤ grand total | `Bill` |
| `PAID` status requires full payment | `Bill` |
| Discharge requires time **and** summary | both layers |
| Discharge cannot precede admission | `PatientCase` |
| Vitals physiological bounds; systolic > diastolic | both layers |
| ICU + emergency ≤ sanctioned beds | both layers |
| Geo coordinates within valid ranges | `GeoLocation` |
| Medical staff require registration number | both layers |
| Password: 10+ chars, mixed case, digit | `auth.py` |
| Stored password must be an Argon2 hash | `User` |
| `UserResponse` / `PatientResponse` carry no credentials or National ID | response schemas |
| Hospital-scoped roles require `hospital_id`; others forbid it | `User` |
| Partial updates must change something | every `*UpdateRequest` |

---

## 6. Phase Status

### Phase 1 - Complete

- 12 Beanie document models + value objects
- 14 Pydantic v2 schema modules
- FastAPI app factory, lifespan, health endpoints
- 412 unit tests, 95% coverage, `mypy --strict` clean, `ruff` clean

### Phase 2 - Complete

- **Service layer**, 15 modules. Framework-free: they raise `DomainError`, never
  `HTTPException`, so the same function is callable from a router, a seed script, or a
  scheduled job.
- **76 routes across 14 routers**, every one returning the `ApiResponse` envelope.
- **JWT authentication** with five-role authorisation. Tokens are re-checked against the
  stored account on every request, so deactivating a user takes effect immediately rather
  than at token expiry.
- **Hospital-scope isolation** enforced twice: in the path dependency and again inside
  every service, so a caller that bypasses the router still cannot read across hospitals.
- **`.xlsx`/`.csv` bulk parser** reading every cell as raw text.
- **Evidence storage** on local disk behind one interface, so an S3 or GridFS swap is
  confined to `storage_service.py`.
- **Audit logging** on the `unhp.audit` logger. Deliberately not a thirteenth collection:
  an audit trail belongs in append-only infrastructure the application cannot rewrite.
- **91 integration tests** against a live MongoDB, alongside the 414 DB-free unit tests.
- **Three-portal dashboard** in `frontend/`, wired to the live API.

### Four defects a live database found

Phase 1's unit tests could not have caught any of these, because none of them appear
until a document makes a real round trip:

| Defect | Consequence had it shipped |
|---|---|
| Beanie stores `Decimal` as BSON `Decimal128`, which Pydantic refuses on read | Every invoice was write-only. Fixed with the `Money` type in `domain/types.py`. |
| MongoDB returns naive datetimes | Every validator comparing a stored timestamp against `utcnow()` raised `TypeError`. Fixed with `tz_aware` clients. |
| Services accepted a `Settings` override the routers never passed | National ID encryption silently used the process singleton. |
| `validate_assignment` fires per field | A discharge, which must move `status` and `discharged_at` together, could not be expressed. Added `apply_atomic_update`. |

### One Phase 1 model amendment

`User` gained a protected `national_id` and an `address`. Citizen registration collected
both and had nowhere to store them, and the PHR cannot unify records across hospitals
without the National ID lookup hash. `UserResponse` is unchanged, so neither field can
leak. Still exactly 12 collections.

### Deferred beyond Phase 2

| Item | Note |
|---|---|
| Object storage for evidence | Local disk works; S3 or GridFS is a one-file change |
| Transactional bed allocation | Needs a replica set. Writes are ordered to fail safe instead |
| The 7-module analytics engine | Phase 4+. Every model was shaped for it |

---

## 7. Commands

```bash
# Backend
uvicorn src.main:app --reload          # start the API on :8000
python -m scripts.seed --reset         # synthetic demonstration data
pytest                                 # 505 tests (unit + integration)
pytest -m "not integration"            # unit tests only, no MongoDB needed
pytest --cov=src --cov-report=term-missing
mypy src/                              # strict type check
ruff check --fix . && ruff format .    # lint + format

# Frontend
cd frontend && npm install
npm run dev                            # dashboard on :3000
npm run build && npm run lint
```

Integration tests need MongoDB on `localhost:27017`. They use a throwaway `unhp_test`
database, dropped at the start and end of the session.

See `DESIGN.md` for the dashboard's design system.

Copy `.env.example` to `.env` and generate real secrets before running outside development:

```bash
python -c "import base64,os;print(base64.urlsafe_b64encode(os.urandom(32)).decode())"
```

Settings refuse to load in staging or production while the `.env.example` placeholders are
still in place.
