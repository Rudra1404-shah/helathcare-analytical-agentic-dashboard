# Healthcare Backend - Claude Code Guidelines

## Domain & HIPAA Compliance Rules
1. **Zero PHI**: Never hardcode real patient records or credentials in tests/code.
2. **Audit Logging**: Every read/write on clinical records must emit structured audit events.
3. **FHIR Standards**: Use HL7 FHIR R4 standard structures via `fhir.resources` or Pydantic V2 schemas.
4. **Type Safety**: Full type annotations on all functions; strict Mypy checks.

## Core Commands
- Start API: `uvicorn src.main:app --reload`
- Run Tests: `pytest`
- Lint/Format: `ruff check --fix . && ruff format .`
- Type Check: `mypy src/`

## ECC Workflow Instructions
- Plan architectural and data model changes before writing code using `/plan`.
- Implement business logic, clinical calculations, and services using `/tdd`.
- Run `/security-review` on any patient-data endpoints and authentication logic.
