# Unified National Health Platform — Claude Code Guidelines

Backend for a national platform bridging public and private healthcare: hospital governance,
hospital operations, unified patient records, and public grievance resolution.

Read `PROJECT_SPEC.md` for the full problem statement, all 17 forms, and the collection catalog.

## Stack

FastAPI · MongoDB · **Beanie 2.2 ODM** · **PyMongo `AsyncMongoClient`** · Pydantic v2 · Python 3.11

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

## Testing

- **Unit tests must not require MongoDB.** `tests/conftest.py` registers every document with
  Beanie without contacting a server. If `test_bootstrap.py` starts failing with
  `CollectionWasNotInitialized`, a Beanie upgrade changed the internal that conftest stubs.
- Build test objects with `tests/factories.py`; override only the field under test.
- AAA structure (Arrange / Act / Assert), descriptive test names stating the behaviour.
- Coverage minimum **80%**; currently 95%.
- Tests needing a live database go in `tests/integration/` and are marked
  `@pytest.mark.integration`.

## Commands

```bash
uvicorn src.main:app --reload          # start API
pytest                                 # run tests
pytest --cov=src --cov-report=term-missing
mypy src/                              # must be clean
ruff check --fix . && ruff format .
```

## Definition of Done

- [ ] `pytest` green
- [ ] `mypy --strict src/` clean
- [ ] `ruff check .` clean
- [ ] Coverage ≥ 80%
- [ ] No plaintext credentials or National IDs anywhere
- [ ] New collections registered in `ALL_DOCUMENT_MODELS`

## Workflow

- Plan architectural and data model changes with `/plan` before writing code.
- Implement business logic and clinical calculations with `/tdd`.
- Run `/security-review` on any patient-data endpoint or authentication logic.

## Git

**The parent directory `Healthcare/` is inside a git repository rooted at the user's home
directory.** Run every git command from inside this project directory. Never `git add` or
`git commit` from `Healthcare/` or above — doing so would stage the entire home directory,
including shell history and credential files.
