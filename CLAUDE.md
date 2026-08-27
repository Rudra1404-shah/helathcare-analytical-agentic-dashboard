# Unified National Health Platform — Claude Code Guidelines

Backend for a national platform bridging public and private healthcare: hospital governance,
hospital operations, unified patient records, and public grievance resolution.

Read `PROJECT_SPEC.md` for the full problem statement, all 17 forms, and the collection catalog.

## Stack

**Backend:** FastAPI · MongoDB · **Beanie 2.2 ODM** · **PyMongo `AsyncMongoClient`** ·
Pydantic v2 · Python 3.11

**Frontend** (`frontend/`): Next.js 16 App Router · Tailwind v4 · shadcn/ui idiom ·
Lucide · Geist. See `DESIGN.md` before touching any of it.

> **Not Motor.** Beanie 2.x dropped Motor; MongoDB folded async support back into PyMongo and
> Motor is end-of-life. `AsyncMongoClient` is the current async driver. Do not add `motor` as a
> dependency.

## Domain & Compliance Rules

1. **Zero PHI.** Never hardcode real patient records, staff details, or credentials in code or
   tests. Use `tests/factories.py`, which is entirely synthetic.
2. **National IDs are never stored in plaintext.** Use `ProtectedNationalId.protect()`, which
   produces AES-GCM ciphertext plus a deterministic HMAC lookup hash. Never add a plaintext
   National ID field to a document, and never expose one on a response schema.
3. **Passwords are never stored in plaintext.** Use `src.core.security.hash_password` (Argon2id).
   The `User` model rejects anything that is not an Argon2 hash.
4. **Response schemas must not carry credentials or National IDs.** `UserResponse` and
   `PatientResponse` have no such fields, deliberately. There are tests asserting this — do not
   "fix" them by adding the field.
5. **Audit logging.** Every read or write on a clinical record must emit a structured audit event
   once the service layer exists (Phase 2).
6. **Type safety.** Full annotations everywhere. `mypy --strict src/` must stay clean.

## Data Modelling Rules

- **Every document extends `TimestampedDocument`** (`src/domain/models/base.py`), which supplies
  `created_at`/`updated_at` and sets `validate_assignment=True`. Validators must guard mutation,
  not just construction.
- **Register new collections in `ALL_DOCUMENT_MODELS`** (`src/domain/models/__init__.py`).
  A model missing from that list is never initialised and fails at runtime.
- **Use `PydanticObjectId` for references, not Beanie `Link`.** Links need a live connection to
  resolve and invite N+1 fetches.
- **Enums live in `src/domain/enums.py`.** Never inline a string literal for a role, status, or
  category anywhere else.
- **Reusable constrained types live in `src/domain/types.py`.** Add to it rather than repeating a
  regex.
- **Money is `Decimal`, never `float`.** Round through `src.domain.models.bill.money`.
  A billing rounding drift becomes an Overcharging complaint.
- **Embedded value objects extend `ValueObject`** and are frozen. Build a new one rather than
  mutating.
- **Declare indexes as `ClassVar[list[IndexModel]]`** inside `class Settings`. Scope uniqueness to
  the hospital via compound indexes where the real-world rule is per-hospital (MRN, employee ID,
  department code, case number, invoice number).

## Validation Rules

Enforce business-critical rules on **both** the request schema and the stored model. The schema
gives the API a clear early failure; the model guarantees no code path bypasses it. The
mandatory-evidence rule on complaints is the reference example — see `PROJECT_SPEC.md` §4.

Raise validation errors with a domain-specific message assigned to `msg`, then
`raise ValueError(msg)`. Say what is wrong and why it matters, not just which constraint failed.

## Driver Boundary

`src/infrastructure/database.py` is the **only** module permitted to import from `pymongo`
directly for connection handling (index declarations aside). Everything else goes through Beanie
documents. This keeps a future driver migration to a single file.

**`tz_aware=True` is not optional on any client.** BSON stores datetimes without a zone, so a
naive client hands back naive values, and every validator comparing a stored timestamp against
`utcnow()` raises `TypeError` on the first document it reads back. Any new client, including one
in a test fixture, sets it.

## Service Layer

`src/services/` owns the business rules. Services:

- **Raise `DomainError`, never `HTTPException`.** The same function has to be callable from a
  router, a seed script, and a scheduled job. `src/api/errors.py` does the HTTP translation.
- **Take an explicit actor** and enforce hospital scope through `hospital_scope_of` even though
  the router already checked. A future caller that bypasses the router must not read across
  hospitals.
- **Accept an optional `Settings`** and the router **must pass it**. A service that falls back to
  the process singleton silently ignores a per-request override, which is how National ID
  encryption once ended up using the wrong key in tests.
- **Emit an audit event** on every clinical read and write, through `src.core.audit`.

### Multi-field transitions

`validate_assignment=True` is right for a single-field edit and wrong for a transition where two
fields must move together. Discharging a case is the reference example: `status` alone is invalid
without `discharged_at`, and `discharged_at` alone is invalid while the status is still open, so
neither order works. Use `apply_atomic_update`, which validates the merged state in one pass.

### Money crosses the driver boundary as Decimal128

Beanie serialises a Python `Decimal` into BSON `Decimal128`, and Pydantic refuses to validate
that type on the way back. Every persisted monetary field uses the `Money` type from
`src.domain.types`, which accepts it. A field typed plain `Decimal` is write-only.

## API Layer

- Every endpoint returns `ApiResponse`. `src/api/errors.py` normalises FastAPI's own errors,
  Pydantic failures, and unhandled exceptions into the same envelope, so a client parses one
  shape whatever happened.
- An unhandled exception answers with a fixed sentence and logs the real cause. An exception
  message can carry a National ID or a connection string.
- Authentication resolves the token and then re-reads the stored account, so deactivating a user
  takes effect immediately rather than at token expiry.

## Testing

- **Unit tests must not require MongoDB.** `tests/conftest.py` registers every document with
  Beanie without contacting a server. If `test_bootstrap.py` starts failing with
  `CollectionWasNotInitialized`, a Beanie upgrade changed the internal that conftest stubs.
- **Integration tests need a live MongoDB** on `localhost:27017`. They live in
  `tests/integration/`, use a throwaway `unhp_test` database dropped at both ends of the
  session, and build their fixtures through the real HTTP endpoints, so the scaffolding is
  itself a test.
- Four defects reached Phase 2 that unit tests could not have caught, because none of them
  appear until a document makes a real round trip. **Anything touching persistence needs an
  integration test**, not only a unit test.
- Tests must not read a developer's local `.env`. `tests/conftest.py` clears it for the session;
  without that, running the API locally is enough to break the placeholder-secret guard tests.
- Build test objects with `tests/factories.py`; override only the field under test.
- AAA structure (Arrange / Act / Assert), descriptive test names stating the behaviour.
- Coverage minimum **80%**; currently 86%.
- Never assert on a substring of a whole serialised response. A random ObjectId hex can contain
  any four digits you were looking for, which makes the test flaky.

## Commands

```bash
# Backend
uvicorn src.main:app --reload          # start the API on :8000
python -m scripts.seed --reset         # synthetic demonstration data
pytest                                 # unit + integration
pytest -m "not integration"            # no MongoDB required
pytest --cov=src --cov-report=term-missing
mypy src/                              # must be clean
ruff check --fix . && ruff format .

# Frontend
cd frontend && npm run dev             # dashboard on :3000
npm run build && npm run lint          # both must be clean
```

## Definition of Done

- [ ] `pytest` green, including integration tests
- [ ] `mypy --strict src/` clean
- [ ] `ruff check .` clean
- [ ] Coverage ≥ 80%
- [ ] No plaintext credentials or National IDs anywhere
- [ ] New collections registered in `ALL_DOCUMENT_MODELS`
- [ ] Clinical reads and writes emit an audit event
- [ ] Frontend: `npm run build` and `npm run lint` clean, and the view has loading, empty, and
      error states, not just its loaded state

## Workflow

- Plan architectural and data model changes with `/plan` before writing code.
- Implement business logic and clinical calculations with `/tdd`.
- Run `/security-review` on any patient-data endpoint or authentication logic.

## Git

**The parent directory `Healthcare/` is inside a git repository rooted at the user's home
directory.** Run every git command from inside this project directory. Never `git add` or
`git commit` from `Healthcare/` or above — doing so would stage the entire home directory,
including shell history and credential files.
